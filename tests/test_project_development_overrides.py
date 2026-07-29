"""End-to-end coverage for explicit project-level development overrides."""

from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

import neuralspotx.operations as operations
from neuralspotx import NSXIntegrityError, NSXResolutionError, load_registry, lock_app, sync_app
from neuralspotx.nsx_lock import LockKind, hash_tree

_MODULE_NAME = "nsx-tflite-micro"
_PROJECT_NAME = "nsx-tflite-micro"
_METADATA_PATH = "modules/nsx-tflite-micro/nsx-module.yaml"


def _write_module_project(root: Path, marker: str) -> None:
    root.mkdir(parents=True)
    (root / "nsx-module.yaml").write_text(
        "\n".join([
            "schema_version: 1",
            "module:",
            f"  name: {_MODULE_NAME}",
            "  type: runtime",
            '  version: "0.1.0"',
            "support:",
            "  ambiqsuite: true",
            "  zephyr: false",
            "build:",
            "  cmake:",
            "    package: nsx_tflite_micro",
            "    targets: [nsx::tflite_micro]",
            "depends:",
            "  required: []",
            "  optional: []",
            "compatibility:",
            '  boards: ["*"]',
            '  socs: ["*"]',
            '  toolchains: ["arm-none-eabi-gcc"]',
        ])
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(marker + "\n", encoding="utf-8")


def _project_override(source: Path, revision: str) -> dict[str, Any]:
    return {
        "projects": {
            _PROJECT_NAME: {
                "name": _PROJECT_NAME,
                "local_path": str(source),
                "revision": revision,
                "path": f"modules/{_PROJECT_NAME}",
            }
        },
        "modules": {
            _MODULE_NAME: {
                "project": _PROJECT_NAME,
                "revision": revision,
                "metadata": _METADATA_PATH,
            }
        },
    }


def _write_app(
    app_dir: Path,
    *,
    layers: list[object],
    revision: str,
    app_override: dict[str, Any] | None = None,
) -> None:
    app_dir.mkdir(exist_ok=True)
    config: dict[str, Any] = {
        "schema_version": 2,
        "project": {"name": "development-override-test"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "baseline": "none",
        "modules": [
            {
                "name": _MODULE_NAME,
                "project": _PROJECT_NAME,
                "revision": revision,
            }
        ],
        "registry": {"layers": layers},
    }
    if app_override is not None:
        config["module_registry"] = app_override
    (app_dir / "nsx.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )


def _write_workspace_overlay(path: Path, override: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump({"schema_version": 1, **override}, sort_keys=False),
        encoding="utf-8",
    )


def test_inline_layer_wins_over_workspace_layer_during_lock(tmp_path: Path) -> None:
    workspace_source = tmp_path / "workspace-sdk"
    inline_source = tmp_path / "inline-sdk"
    _write_module_project(workspace_source, "workspace")
    _write_module_project(inline_source, "inline")

    app_dir = tmp_path / "app"
    workspace_overlay = app_dir / "workspace-registry.yaml"
    app_dir.mkdir()
    _write_workspace_overlay(
        workspace_overlay,
        _project_override(workspace_source, "workspace-branch"),
    )
    _write_app(
        app_dir,
        layers=[
            "packaged",
            {"workspace": workspace_overlay.name},
            {"inline": _project_override(inline_source, "inline-branch")},
        ],
        revision="inline-branch",
    )

    lock = lock_app(app_dir, quiet=True)
    module = lock.modules[_MODULE_NAME]

    assert module.kind == LockKind.LOCAL
    assert module.constraint == "inline-branch"
    assert module.content_hash == hash_tree(inline_source)
    assert module.content_hash != hash_tree(workspace_source)


def test_workspace_local_path_is_relative_to_overlay_not_process_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sdk"
    overlay_dir = tmp_path / "configuration"
    app_dir = tmp_path / "app"
    unrelated_cwd = tmp_path / "elsewhere"
    _write_module_project(source, "workspace-relative")
    overlay_dir.mkdir()
    unrelated_cwd.mkdir()

    override = _project_override(source, "workspace-branch")
    override["projects"][_PROJECT_NAME]["local_path"] = "../sdk"
    _write_workspace_overlay(overlay_dir / "registry.yaml", override)
    _write_app(
        app_dir,
        layers=[{"workspace": "../configuration/registry.yaml"}],
        revision="workspace-branch",
    )
    monkeypatch.chdir(unrelated_cwd)

    lock = lock_app(app_dir, quiet=True)
    module = lock.modules[_MODULE_NAME]

    assert module.kind == LockKind.LOCAL
    assert module.content_hash == hash_tree(source)


def test_app_local_override_wins_over_registry_layers_and_records_local_sdk(
    tmp_path: Path,
) -> None:
    workspace_source = tmp_path / "workspace-sdk"
    inline_source = tmp_path / "inline-sdk"
    app_source = tmp_path / "app-sdk"
    _write_module_project(workspace_source, "workspace")
    _write_module_project(inline_source, "inline")
    _write_module_project(app_source, "app-local")

    app_dir = tmp_path / "app"
    workspace_overlay = app_dir / "workspace-registry.yaml"
    app_dir.mkdir()
    _write_workspace_overlay(
        workspace_overlay,
        _project_override(workspace_source, "workspace-branch"),
    )
    _write_app(
        app_dir,
        layers=[
            {"workspace": workspace_overlay.name},
            {"inline": _project_override(inline_source, "inline-branch")},
        ],
        revision="app-branch",
        app_override=_project_override(app_source, "app-branch"),
    )

    lock = lock_app(app_dir, quiet=True)
    module = lock.modules[_MODULE_NAME]

    assert module.project == _PROJECT_NAME
    assert module.kind == LockKind.LOCAL
    assert module.constraint == "app-branch"
    assert module.content_hash == hash_tree(app_source)
    assert module.commit is None


def test_branch_override_locks_real_commit_without_mutating_stable_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    branch = "bringup/customer-board"
    repo = tmp_path / "sdk-repository"
    _write_module_project(repo, "committed development SDK")
    _initialize_git_repository(repo, branch)
    commit = _git_output(repo, "rev-parse", "HEAD")

    app_dir = tmp_path / "app"
    app_module_dir = app_dir / "modules" / _PROJECT_NAME
    app_module_dir.parent.mkdir(parents=True)
    shutil.copytree(repo, app_module_dir, ignore=shutil.ignore_patterns(".git"))

    remote_url = "https://example.invalid/nsx-tflite-micro.git"
    git_override = {
        "projects": {
            _PROJECT_NAME: {
                "url": remote_url,
                "revision": branch,
                "path": f"modules/{_PROJECT_NAME}",
            }
        },
        "modules": {
            _MODULE_NAME: {
                "project": _PROJECT_NAME,
                "revision": branch,
                "metadata": _METADATA_PATH,
            }
        },
    }
    _write_app(
        app_dir,
        layers=[{"inline": git_override}],
        revision=branch,
    )

    packaged_registry = load_registry()
    stable_defaults = copy.deepcopy({
        "project": packaged_registry["projects"][_PROJECT_NAME],
        "module": packaged_registry["modules"][_MODULE_NAME],
    })
    calls: list[tuple[str, str, str]] = []

    def resolve_ref(url: str, ref: str) -> tuple[str, str]:
        calls.append(("resolve", url, ref))
        return commit, "branch"

    def hash_git_artifact(url: str, resolved_commit: str) -> str:
        calls.append(("hash", url, resolved_commit))
        return hash_tree(repo)

    monkeypatch.setattr(operations._lock, "resolve_ref", resolve_ref)
    monkeypatch.setattr(operations._lock, "hash_git_artifact", hash_git_artifact)

    lock = lock_app(app_dir, quiet=True, resolve_ttl_s=0)
    module = lock.modules[_MODULE_NAME]

    assert module.kind == LockKind.GIT
    assert module.constraint == branch
    assert module.commit == commit
    assert module.tag is None
    assert module.content_hash == hash_tree(repo)
    assert calls == [
        ("resolve", remote_url, branch),
        ("hash", remote_url, commit),
    ]
    assert packaged_registry["projects"][_PROJECT_NAME] == stable_defaults["project"]
    assert packaged_registry["modules"][_MODULE_NAME] == stable_defaults["module"]

    sync_app(app_dir, frozen=True)
    (app_module_dir / "README.md").write_text("drifted\n", encoding="utf-8")
    with pytest.raises(NSXIntegrityError) as exc:
        sync_app(app_dir, frozen=True)
    assert exc.value.module == _MODULE_NAME


def test_local_path_overrides_packaged_neuralspotx_project(tmp_path: Path) -> None:
    source = tmp_path / "neuralspotx-checkout"
    metadata = source / "src" / "neuralspotx" / "cmake" / "nsx-module.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "\n".join([
            "schema_version: 1",
            "module:",
            "  name: nsx-tooling",
            "  type: tooling",
            '  version: "0.1.0"',
            "support:",
            "  ambiqsuite: true",
            "  zephyr: false",
            "build:",
            "  cmake:",
            "    package: nsx_tooling",
            "    targets: [nsx::tooling]",
            "depends:",
            "  required: []",
            "  optional: []",
            "compatibility:",
            '  boards: ["*"]',
            '  socs: ["*"]',
            '  toolchains: ["arm-none-eabi-gcc"]',
        ])
        + "\n",
        encoding="utf-8",
    )
    (source / "LOCAL_CHECKOUT.txt").write_text("local packaged override\n", encoding="utf-8")

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    config = {
        "schema_version": 2,
        "project": {"name": "packaged-local-override"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "baseline": "none",
        "modules": [
            {
                "name": "nsx-tooling",
                "project": "neuralspotx",
                "revision": "local-checkout",
            }
        ],
        "module_registry": {
            "projects": {
                "neuralspotx": {
                    "local_path": str(source),
                    "revision": "local-checkout",
                }
            },
            "modules": {
                "nsx-tooling": {
                    "project": "neuralspotx",
                    "revision": "local-checkout",
                    "metadata": "src/neuralspotx/cmake/nsx-module.yaml",
                }
            },
        },
    }
    (app_dir / "nsx.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    stale_metadata = (
        app_dir
        / "modules"
        / "neuralspotx"
        / "src"
        / "neuralspotx"
        / "cmake"
        / "nsx-module.yaml"
    )
    stale_metadata.parent.mkdir(parents=True)
    stale_metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            "  required: []",
            "  required: [stale-mirror-only-dependency]",
        ),
        encoding="utf-8",
    )

    lock = lock_app(app_dir, quiet=True)
    module = lock.modules["nsx-tooling"]

    assert list(lock.modules) == ["nsx-tooling"]
    assert module.kind == LockKind.LOCAL
    assert module.constraint == "local-checkout"
    assert module.content_hash == hash_tree(source)
    assert Path(module.vendored_at).as_posix() == "modules/neuralspotx"

    sync_app(app_dir)
    assert (app_dir / "modules" / "neuralspotx" / "LOCAL_CHECKOUT.txt").is_file()
    modules_cmake = (app_dir / "cmake" / "nsx" / "modules.cmake").read_text(
        encoding="utf-8"
    )
    assert (
        'set(NSX_APP_MODULE_DIR_nsx_tooling "modules/neuralspotx/src/neuralspotx/cmake")'
        in modules_cmake
    )
    gitignore = (app_dir / "modules" / ".gitignore").read_text(encoding="utf-8")
    assert "neuralspotx/" in gitignore
    assert "nsx-tooling/" not in gitignore
    sync_app(app_dir, frozen=True)


def test_local_path_missing_metadata_does_not_fall_back_to_packaged_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "incomplete-neuralspotx-checkout"
    source.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    config = {
        "schema_version": 2,
        "project": {"name": "missing-local-metadata"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "baseline": "none",
        "modules": [{"name": "nsx-tooling"}],
        "module_registry": {
            "projects": {
                "neuralspotx": {
                    "local_path": str(source),
                    "revision": "local-checkout",
                    "path": "modules/neuralspotx",
                }
            }
        },
    }
    (app_dir / "nsx.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(NSXResolutionError) as exc:
        lock_app(app_dir, quiet=True)

    assert "explicit local project 'neuralspotx'" in str(exc.value)
    assert str(source / "src" / "neuralspotx" / "cmake" / "nsx-module.yaml") in str(
        exc.value
    )


def _initialize_git_repository(repo: Path, branch: str) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "nsx-tests@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "NSX Tests"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "checkout", "-b", branch], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "test SDK"], cwd=repo, check=True, capture_output=True)


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
