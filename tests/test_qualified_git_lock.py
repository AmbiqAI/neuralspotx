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


def test_cold_plain_lock_discovers_dependencies_from_pinned_commit(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    manifest["modules"] = [{"name": "driver"}]
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    driver = tmp_path / "origins/driver"
    metadata = driver / "nsx-module.yaml"
    old_bytes = metadata.read_bytes()
    definition = yaml.safe_load(old_bytes)
    definition["depends"]["required"] = ["sdk"]
    metadata.write_bytes(yaml.safe_dump(definition).encode())
    git(driver, "commit", "-am", "require SDK")
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    original = pins(tmp_path)
    assert all(set(rows) == {"driver", "sdk"} for rows in original.values())
    metadata.write_bytes(old_bytes)
    git(driver, "commit", "-am", "remove SDK dependency")
    shutil.rmtree(tmp_path / "modules")
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert pins(tmp_path) == original
    shutil.rmtree(tmp_path / "modules")
    assert cli.main(["sync", "--app-dir", str(tmp_path), "--frozen"]) == 0


def test_authored_project_provides_sole_module_revision(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    sdk_project = registry["projects"].pop("sdk")
    sdk_module = registry["modules"].pop("sdk")
    del sdk_module["revision"]
    sdk_project["revision"] = "v1"
    manifest["module_registry"] = {"projects": {"sdk": sdk_project}, "modules": {"sdk": sdk_module}}
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    sdk = tmp_path / "origins/sdk"
    expected = advance(sdk)
    git(sdk, "tag", "v2")
    sdk_project["revision"] = "v2"
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert all(rows["sdk"][0] == expected for rows in pins(tmp_path).values())


def test_targeted_update_can_adopt_packaged_replacement(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    manifest["modules"] = [{"name": "driver"}, {"name": "nsx-tooling"}]
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    packaged = registry["modules"]["nsx-tooling"]
    registry["modules"]["nsx-tooling"] = registry["modules"]["sdk"]
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    before = pins(tmp_path)
    advance(tmp_path / "origins/driver")
    registry["modules"]["nsx-tooling"] = packaged
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) != 0
    assert cli.main(["lock", "--app-dir", str(tmp_path), "--module", "nsx-tooling"]) == 0
    lock = read_lock_file(tmp_path)
    assert lock is not None
    for board, target in lock.targets.items():
        assert target.modules["nsx-tooling"].kind == "packaged"
        assert target.modules["driver"].commit == before[board]["driver"][0]


def test_board_specific_metadata_after_cold_targeted_update(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    from neuralspotx.operations import lock_app_impl, sync_app_impl

    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    manifest["modules"] = [{"name": "driver"}]
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    driver = tmp_path / "origins/driver"
    metadata = driver / "nsx-module.yaml"
    definition = yaml.safe_load(metadata.read_bytes())
    definition["depends"]["required"] = ["sdk"]
    metadata.write_bytes(yaml.safe_dump(definition).encode())
    git(driver, "commit", "-am", "require SDK")
    shutil.rmtree(tmp_path / "modules")
    updated = lock_app_impl(tmp_path, board=BOARDS[1], update=True, modules=["driver"])
    assert updated.modules["driver"].commit == git(driver, "rev-parse", "HEAD")
    assert "sdk" in updated.modules
    before = pins(tmp_path)
    assert "sdk" not in before[BOARDS[0]]
    shutil.rmtree(tmp_path / "modules")
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert pins(tmp_path) == before
    for board in BOARDS:
        if (tmp_path / "modules").exists():
            shutil.rmtree(tmp_path / "modules")
        sync_app_impl(tmp_path, board=board, frozen=True)
