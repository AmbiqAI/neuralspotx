"""Read an unmodified schema-6 lock written once by the baseline CLI at 58596db.

The fixture uses fixed Git identities and timestamps so both commits in the receipt
are reproducible on every host. Tests copy the committed receipt before invoking
the candidate CLI. Updating the freeze baseline is a deliberate fixture change.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import cli, project_config
from neuralspotx.nsx_lock import read_lock_file
from neuralspotx.subprocess_utils import _git

FIXTURE = Path(__file__).parent / "fixtures/qualified-lock"
BOARDS = ("apollo510_evb", "apollo510b_evb")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    registry = project_config._load_registry()
    config = tmp_path / "gitconfig"
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_DATE", "2026-01-01T00:00:00+0000")
        monkeypatch.setenv(f"GIT_{role}_NAME", "NSX fixture")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NSX_RESOLVE_TTL", "0")
    monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", "1")
    # Production Git validation sees the two HTTPS URLs recorded in the lock.
    # Only this test permits the rewritten file transport.
    monkeypatch.setattr(_git, "GIT_PROTOCOL_ALLOWLIST_FLAGS", ("-c", "protocol.file.allow=always"))
    shutil.copyfile(FIXTURE / "nsx.yml", tmp_path / "nsx.yml")
    for name in ("driver", "sdk"):
        repo = tmp_path / "origins" / name
        repo.mkdir(parents=True)
        url = f"https://fixture.invalid/{name}.git"
        git(repo, "config", "--global", f"url.{repo.as_uri()}.insteadOf", url)
        git(repo, "init", "-b", "main")
        git(repo, "config", "core.filemode", "false")
        meta = {
            "schema_version": 1,
            "module": {"name": name, "type": "runtime", "version": "1.0.0"},
            "support": {"ambiqsuite": True, "zephyr": False},
            "build": {"cmake": {"package": name, "targets": [f"nsx::{name}"]}},
            "depends": {"required": [], "optional": []},
            "compatibility": {"boards": ["*"], "socs": ["*"], "toolchains": ["arm-none-eabi-gcc"]},
        }
        (repo / "nsx-module.yaml").write_bytes(yaml.safe_dump(meta, sort_keys=False).encode())
        (repo / "revision.txt").write_bytes(b"qualified\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "qualified")
        git(repo, "tag", "v1")
        registry["projects"][name] = {"url": url, "path": f"modules/{name}"}
        registry["modules"][name] = {
            "project": name,
            "revision": "main" if name == "driver" else "v1",
            "metadata": "nsx-module.yaml",
        }
    monkeypatch.setattr(project_config, "load_registry_lock", lambda _path: registry)
    return registry


def pins(app: Path) -> dict[str, dict[str, tuple[str | None, str]]]:
    lock = read_lock_file(app)
    assert lock is not None
    return {
        board: {name: (row.commit, row.content_hash) for name, row in section.modules.items()}
        for board, section in lock.targets.items()
    }


def advance(repo: Path) -> str:
    (repo / "revision.txt").write_bytes(b"updated\n")
    git(repo, "commit", "-am", "next")
    return git(repo, "rev-parse", "HEAD")


def test_qualified_lock_lifecycle(
    tmp_path: Path,
    registry: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = tmp_path / "nsx.lock"
    shutil.copyfile(FIXTURE / "nsx.lock", receipt)

    def nsx(command: str, *flags: str) -> int:
        return cli.main([command, "--app-dir", str(tmp_path), *flags])

    initial = pins(tmp_path)
    driver = tmp_path / "origins/driver"
    sdk = tmp_path / "origins/sdk"
    new_driver = advance(driver)
    new_sdk = advance(sdk)
    git(sdk, "tag", "v2")
    for board in BOARDS:
        assert initial[board]["driver"][0] == git(driver, "rev-parse", "v1")
        assert initial[board]["sdk"][0] == git(sdk, "rev-parse", "v1")
    assert nsx("sync", "--frozen") == 0
    assert receipt.read_bytes() == (FIXTURE / "nsx.lock").read_bytes()
    assert nsx("lock") == 0
    assert pins(tmp_path) == initial

    baseline = receipt.read_bytes()
    # Failure after board one has prepared a genuine change cannot publish it.
    from neuralspotx.operations import _lock

    write_module_file = _lock._write_app_module_file

    def fail_second_board(app_dir, cfg, *, module_names):
        if cfg["target"]["board"] == BOARDS[1]:
            raise OSError("second board build inputs unavailable")
        write_module_file(app_dir, cfg, module_names=module_names)

    with monkeypatch.context() as patch:
        patch.setattr(_lock, "_write_app_module_file", fail_second_board)
        assert nsx("lock", "--module", "driver") != 0
    assert receipt.read_bytes() == baseline
    assert nsx("lock", "--module", "driver") == 0
    for board, rows in pins(tmp_path).items():
        assert rows["driver"][0] == new_driver
        assert rows["sdk"] == initial[board]["sdk"]

    registry["modules"]["sdk"]["revision"] = "v2"
    before = receipt.read_bytes()
    for flags in ((), ("--module", "driver")):
        capsys.readouterr()
        assert nsx("lock", *flags) != 0
        message = capsys.readouterr().err
        assert all(board in message for board in BOARDS)
        assert "nsx lock --module sdk" in message
        assert receipt.read_bytes() == before
    assert nsx("lock", "--module", "sdk") == 0
    assert all(rows["sdk"][0] == new_sdk for rows in pins(tmp_path).values())


def test_compatible_default_and_workspace_pin(tmp_path: Path, registry: dict[str, Any]) -> None:
    shutil.copyfile(FIXTURE / "nsx.lock", tmp_path / "nsx.lock")
    sdk = tmp_path / "origins/sdk"
    git(sdk, "tag", "alias-for-v1", "v1")
    registry["modules"]["sdk"]["revision"] = "alias-for-v1"
    before = pins(tmp_path)
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert pins(tmp_path) == before

    new_sdk = advance(sdk)
    git(sdk, "tag", "v2")
    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    manifest["registry"] = {"layers": [{"workspace": "pins.yml"}]}
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    (tmp_path / "pins.yml").write_text("projects:\n  sdk:\n    revision: v2\n")
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert all(rows["sdk"][0] == new_sdk for rows in pins(tmp_path).values())
