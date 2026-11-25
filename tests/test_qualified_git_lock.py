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


@pytest.mark.parametrize("empty_revision", [False, True])
def test_authored_project_provides_sole_module_revision(
    tmp_path: Path, registry: dict[str, Any], empty_revision: bool
) -> None:
    manifest = yaml.safe_load((tmp_path / "nsx.yml").read_text())
    sdk_project = registry["projects"].pop("sdk")
    sdk_module = registry["modules"].pop("sdk")
    if empty_revision:
        sdk_module["revision"] = ""
    else:
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
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert cli.main(["lock", "--check", "--app-dir", str(tmp_path)]) == 0
    assert pins(tmp_path) == before
    shutil.rmtree(tmp_path / "modules")
    assert cli.main(["lock", "--check", "--app-dir", str(tmp_path)]) == 0
    assert not (tmp_path / "modules").exists()
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert pins(tmp_path) == before
    for board in BOARDS:
        if (tmp_path / "modules").exists():
            shutil.rmtree(tmp_path / "modules")
        sync_app_impl(tmp_path, board=board, frozen=True)


@pytest.mark.parametrize("nested", [False, True])
def test_new_board_discovers_dependencies_from_its_own_revision(
    tmp_path: Path, registry: dict[str, Any], nested: bool
) -> None:
    from neuralspotx.operations import sync_app_impl

    # An app-relative selector can refer to the default checkout even when
    # the project does not explicitly set its path.
    driver = tmp_path / "origins/driver"
    metadata = driver / "nsx-module.yaml"
    if nested:
        nested_dir = driver / "modules/driver"
        nested_dir.mkdir(parents=True)
        metadata.rename(nested_dir / metadata.name)
        metadata = nested_dir / metadata.name
        git(driver, "add", "-A")
        git(driver, "commit", "-m", "nest module inside repository")
    del registry["projects"]["driver"]["path"]
    registry["modules"]["driver"]["metadata"] = "modules/driver/nsx-module.yaml"
    manifest_path = tmp_path / "nsx.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["modules"] = [{"name": "driver"}]
    manifest["targets"]["supported"] = [BOARDS[0]]
    manifest_path.write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    original = pins(tmp_path)
    definition = yaml.safe_load(metadata.read_bytes())
    definition["depends"]["required"] = ["sdk"]
    metadata.write_bytes(yaml.safe_dump(definition).encode())
    git(driver, "commit", "-am", "require SDK")
    shutil.rmtree(tmp_path / "modules")
    manifest["targets"]["supported"] = list(BOARDS)
    manifest_path.write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    current = pins(tmp_path)
    assert current[BOARDS[0]] == original[BOARDS[0]]
    assert current[BOARDS[1]]["driver"][0] == git(driver, "rev-parse", "HEAD")
    assert "sdk" in current[BOARDS[1]]
    shutil.rmtree(tmp_path / "modules")
    assert cli.main(["lock", "--check", "--app-dir", str(tmp_path)]) == 0
    sync_app_impl(tmp_path, board=BOARDS[1], frozen=True)


@pytest.mark.parametrize("renamed,nested", [(False, False), (True, False), (True, True)])
def test_cold_conflict_reports_qualified_pin_before_new_board_requirements(
    tmp_path: Path,
    registry: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    renamed: bool,
    nested: bool,
) -> None:
    receipt = tmp_path / "nsx.lock"
    shutil.copyfile(FIXTURE / "nsx.lock", receipt)
    sdk = tmp_path / "origins/sdk"
    path = sdk / "nsx-module.yaml"
    baseline = "v1"
    if nested:
        nested_path = sdk / "modules/sdk/nsx-module.yaml"
        nested_path.parent.mkdir(parents=True)
        path.rename(nested_path)
        path = nested_path
        git(sdk, "add", "-A")
        git(sdk, "commit", "-m", "move manifest inside vendor-shaped directory")
        baseline = "nested-v1"
        git(sdk, "tag", baseline)
        registry["modules"]["sdk"]["revision"] = baseline
        registry["modules"]["sdk"]["metadata"] = "modules/sdk/modules/sdk/nsx-module.yaml"
        receipt.unlink()
        assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
        shutil.rmtree(tmp_path / "modules")
    original = receipt.read_bytes()
    meta = yaml.safe_load(path.read_bytes())
    meta["compatibility"]["boards"] = [BOARDS[1]]
    path.write_text(yaml.safe_dump(meta))
    git(sdk, "commit", "-am", "limit supported boards")
    git(sdk, "tag", "v2")
    registry["modules"]["sdk"]["revision"] = "v2"
    project = "sdk"
    if renamed:
        project = "new-sdk"
        registry["projects"][project] = registry["projects"].pop("sdk")
        registry["modules"]["sdk"]["project"] = project
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) != 0
    message = capsys.readouterr().err
    for board in BOARDS:
        assert f"board '{board}', project '{project}'" in message
    assert "nsx lock --module sdk" in message
    assert receipt.read_bytes() == original
    # The old checkout can also have been restored before the update attempt.
    # Neither retry may use its compatibility metadata to approve v2.
    shutil.copytree(sdk, tmp_path / "modules/sdk", dirs_exist_ok=True)
    git(tmp_path / "modules/sdk", "checkout", baseline)
    for flags in (["--module", "sdk"], ["--update"]):
        assert cli.main(["lock", *flags, "--app-dir", str(tmp_path)]) != 0
        assert "incompatible with target" in capsys.readouterr().err
        assert receipt.read_bytes() == original


def test_authored_empty_module_revision_resets_to_main(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    shutil.copyfile(FIXTURE / "nsx.lock", tmp_path / "nsx.lock")
    manifest_path = tmp_path / "nsx.yml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["module_registry"] = {"modules": {"sdk": {"revision": ""}}}
    manifest_path.write_text(yaml.safe_dump(manifest))
    expected = advance(tmp_path / "origins/sdk")
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    assert all(rows["sdk"][0] == expected for rows in pins(tmp_path).values())


@pytest.mark.parametrize("flags", [("--update",), ("--module", "driver")])
def test_cold_update_check_reports_drift_without_vendoring(
    tmp_path: Path,
    registry: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    flags: tuple[str, ...],
) -> None:
    # A workspace registry may include external metadata for another project
    # that no target uses. A cold update check must not inspect or acquire it.
    registry["projects"]["extra"] = {"url": "https://fixture.invalid/unselected.git"}
    registry["modules"]["extra"] = {
        "project": "extra",
        "revision": "main",
        "metadata": str(tmp_path / "external.yaml"),
    }
    receipt = tmp_path / "nsx.lock"
    original = (FIXTURE / "nsx.lock").read_bytes()
    receipt.write_bytes(original)
    advance(tmp_path / "origins/driver")
    assert cli.main(["lock", "--check", *flags, "--app-dir", str(tmp_path)]) != 0
    captured = capsys.readouterr()
    assert "OUT OF DATE" in (captured.out + captured.err), captured
    assert receipt.read_bytes() == original
    assert not (tmp_path / "modules").exists()
    assert not (tmp_path / "build").exists()


def test_update_selects_a_shared_project_only_where_named_module_is_present(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    driver = tmp_path / "origins/driver"
    alias = yaml.safe_load((driver / "nsx-module.yaml").read_bytes())
    alias["module"]["name"] = "alias"
    (driver / "alias.yaml").write_text(yaml.safe_dump(alias))
    git(driver, "add", "alias.yaml")
    git(driver, "commit", "-m", "add module alias")
    registry["modules"]["alias"] = {**registry["modules"]["driver"], "metadata": "alias.yaml"}
    manifest_path = tmp_path / "nsx.yml"
    manifest = yaml.safe_load(manifest_path.read_bytes())
    manifest["modules"] = [{"name": "driver", "boards": [BOARDS[0]]}, {"name": "alias"}]
    manifest_path.write_text(yaml.safe_dump(manifest))
    assert cli.main(["lock", "--app-dir", str(tmp_path)]) == 0
    before = pins(tmp_path)
    updated = advance(driver)
    assert cli.main(["lock", "--module", "driver", "--app-dir", str(tmp_path)]) == 0
    after = pins(tmp_path)
    assert after[BOARDS[0]]["driver"][0] == after[BOARDS[0]]["alias"][0] == updated
    assert after[BOARDS[1]] == before[BOARDS[1]]


def test_clean_reset_and_frozen_restore_from_combined_receipt(
    tmp_path: Path, registry: dict[str, Any]
) -> None:
    receipt = tmp_path / "nsx.lock"
    shutil.copyfile(FIXTURE / "nsx.lock", receipt)
    source = receipt.read_bytes()

    def nsx(command: str, *flags: str) -> int:
        return cli.main([command, "--app-dir", str(tmp_path), *flags])

    assert nsx("sync", "--frozen") == 0
    driver = tmp_path / "modules/driver"
    sdk = tmp_path / "modules/sdk"
    file = sdk / "revision.txt"
    original = file.read_bytes()
    file.write_text("local edits")
    assert nsx("clean", "--reset") == 1
    assert driver.is_dir() and file.read_text() == "local edits"
    assert nsx("clean", "--reset", "--force") == 0
    assert not driver.exists() and not sdk.exists()
    assert nsx("clean", "--reset") == 0
    assert nsx("sync", "--frozen") == 0
    assert driver.is_dir() and file.read_bytes() == original
    assert receipt.read_bytes() == source


@pytest.mark.parametrize("case", ["partial", "stale", "unclassified", "nested", "local-source"])
def test_reset_preserves_uncertain_ownership(
    tmp_path: Path, registry: dict[str, Any], case: str
) -> None:
    receipt = tmp_path / "nsx.lock"
    shutil.copyfile(FIXTURE / "nsx.lock", receipt)
    assert cli.main(["sync", "--app-dir", str(tmp_path), "--frozen"]) == 0
    sdk = tmp_path / "modules/sdk"
    target = sdk / "revision.txt"
    doc = yaml.safe_load(receipt.read_text(encoding="utf-8"))
    section = doc["targets"][BOARDS[1]]
    if case == "partial":
        del doc["targets"][BOARDS[1]]
    elif case == "stale":
        section["manifest"]["hash"] = ""
    elif case == "unclassified":
        section["modules"]["sdk"]["kind"] = "future"
    elif case == "nested":
        section["modules"]["child"] = {
            "kind": "vendored",
            "resolved": {"vendored_at": "modules/sdk/nested"},
        }
    else:
        registry["projects"]["source"] = {"local_path": str(sdk / "nested")}
    receipt.write_text(yaml.safe_dump(doc), encoding="utf-8")
    rc = cli.main(["clean", "--app-dir", str(tmp_path), "--reset", "--force"])
    assert rc == (1 if case == "unclassified" else 0)
    assert target.is_file()


@pytest.mark.parametrize("checkout", ["modules/sdk/nested", "modules/sdk"])
def test_reset_preserves_unlocked_workspace_checkout(
    tmp_path: Path, registry: dict[str, Any], checkout: str
) -> None:
    manifest = tmp_path / "nsx.yml"
    cfg = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    cfg["registry"] = {"layers": [{"workspace": "overlay.yml"}]}
    manifest.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    overlay = tmp_path / "overlay.yml"
    overlay.write_text("projects: {}\n", encoding="utf-8")

    def nsx(*args: str) -> int:
        return cli.main([args[0], "--app-dir", str(tmp_path), *args[1:]])

    assert nsx("lock") == 0
    assert nsx("sync", "--frozen") == 0
    overlay.write_text(
        yaml.safe_dump({
            "projects": {
                "additional": {"url": "https://fixture.invalid/additional.git", "path": checkout}
            }
        }),
        encoding="utf-8",
    )
    source = tmp_path / checkout / "unlocked.c"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"int keep_me;\n")
    assert nsx("clean", "--reset", "--force") == 0
    assert source.read_bytes() == b"int keep_me;\n"
    assert (tmp_path / "modules/sdk/revision.txt").is_file()
    assert not (tmp_path / "modules/driver").exists()


@pytest.mark.parametrize("flags", [(), ("--force",)])
def test_reset_preserves_empty_directories(
    tmp_path: Path, registry: dict[str, Any], flags: tuple[str, ...]
) -> None:
    shutil.copyfile(FIXTURE / "nsx.lock", tmp_path / "nsx.lock")
    assert cli.main(["sync", "--app-dir", str(tmp_path), "--frozen"]) == 0
    empty = tmp_path / "modules/sdk/local-output/logs"
    empty.mkdir(parents=True)
    assert cli.main(["clean", "--app-dir", str(tmp_path), "--reset", *flags]) == 0
    assert empty.is_dir()
    assert not (tmp_path / "modules/driver").exists()
