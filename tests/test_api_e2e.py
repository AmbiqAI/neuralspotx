from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from neuralspotx import (
    AppBuildRequest,
    AppCleanRequest,
    AppCreateRequest,
    ModuleRegisterRequest,
    NSXError,
    WorkspaceInitRequest,
    add_module,
    build_app,
    clean_app,
    cli,
    create_app,
    init_workspace,
    register_module,
    remove_module,
    sync_workspace,
    update_modules,
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_local_module_metadata(path: Path, module_name: str = "local-demo") -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "module:",
                f"  name: {module_name}",
                "  type: runtime",
                '  version: "0.1.0"',
                "support:",
                "  ambiqsuite: true",
                "  zephyr: false",
                "build:",
                "  cmake:",
                "    package: local_demo",
                "    targets: [local_demo]",
                "depends:",
                "  required: []",
                "  optional: []",
                "compatibility:",
                '  boards: ["*"]',
                '  socs: ["*"]',
                '  toolchains: ["arm-none-eabi-gcc"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_local_module_project(root: Path, module_name: str = "local-demo") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    metadata_path = root / "nsx-module.yaml"
    _write_local_module_metadata(metadata_path, module_name=module_name)
    (root / "CMakeLists.txt").write_text("add_library(local_demo INTERFACE)\n", encoding="utf-8")
    (root / "README.md").write_text("version one\n", encoding="utf-8")
    return metadata_path


def test_create_app_requires_initialized_workspace(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="Workspace is not initialized"):
        create_app(tmp_path, "hello_fail", board="apollo510_evb", no_bootstrap=True)


def test_create_app_can_initialize_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_init_workspace_impl(
        workspace: Path,
        *,
        nsx_repo_url: str | None = None,
        nsx_revision: str = "main",
        ambiqsuite_repo_url: str | None = None,
        ambiqsuite_revision: str = "main",
        skip_update: bool = False,
    ) -> None:
        del nsx_repo_url, nsx_revision, ambiqsuite_repo_url, ambiqsuite_revision, skip_update
        (workspace / ".west").mkdir(parents=True, exist_ok=True)
        (workspace / "manifest").mkdir(parents=True, exist_ok=True)
        (workspace / "manifest" / "west.yml").write_text("manifest:\n  projects: []\n", encoding="utf-8")

    monkeypatch.setattr(cli, "init_workspace_impl", fake_init_workspace_impl)

    create_app(
        AppCreateRequest(
            workspace=tmp_path,
            name="hello_init",
            board="apollo510_evb",
            init_workspace=True,
            no_bootstrap=True,
        )
    )

    assert (tmp_path / "manifest" / "west.yml").exists()
    assert (tmp_path / "apps" / "hello_init" / "nsx.yml").exists()


def test_init_workspace_and_create_app_round_trip(tmp_path: Path) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))
    create_app(tmp_path, "hello_api", board="apollo510_evb", no_bootstrap=True)

    app_dir = tmp_path / "apps" / "hello_api"
    cfg = _load_yaml(app_dir / "nsx.yml")

    assert cfg["project"]["name"] == "hello_api"
    assert cfg["target"]["board"] == "apollo510_evb"
    assert cfg["modules"] == []
    assert (app_dir / "cmake" / "nsx").exists()


def test_register_local_module_persists_relative_metadata_path(tmp_path: Path) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))
    create_app(tmp_path, "hello_local", board="apollo510_evb", no_bootstrap=True)

    app_dir = tmp_path / "apps" / "hello_local"
    metadata_path = app_dir / "local-module.yaml"
    _write_local_module_metadata(metadata_path)

    register_module(
        ModuleRegisterRequest(
            app_dir=app_dir,
            module="local-demo",
            metadata=metadata_path,
            project="local-demo-proj",
            project_local_path=app_dir,
        )
    )

    cfg = _load_yaml(app_dir / "nsx.yml")
    assert cfg["module_registry"]["modules"]["local-demo"]["metadata"] == "local-module.yaml"
    assert not (app_dir / "modules" / "local-demo").exists()


def test_full_clean_removes_build_directory(tmp_path: Path) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))
    create_app(tmp_path, "hello_clean", board="apollo510_evb", no_bootstrap=True)

    build_dir = tmp_path / "apps" / "hello_clean" / "build" / "apollo510_evb"
    build_dir.mkdir(parents=True)
    (build_dir / "build.ninja").write_text("# fake\n", encoding="utf-8")

    clean_app(
        AppCleanRequest(
            app_dir=tmp_path / "apps" / "hello_clean",
            full=True,
        )
    )

    assert not build_dir.exists()


def test_sync_workspace_uses_shared_impl_without_shelling_from_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))

    calls: list[tuple[list[str], Path | None]] = []

    def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
        calls.append((cmd, cwd))

    monkeypatch.setattr(cli, "_run", fake_run)

    sync_workspace(tmp_path)

    assert calls == [(["west", "update"], tmp_path)]


def test_local_module_round_trip_add_update_remove(tmp_path: Path) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))
    create_app(tmp_path, "hello_modules", board="apollo510_evb", no_bootstrap=True)

    app_dir = tmp_path / "apps" / "hello_modules"
    project_root = tmp_path / "local-projects" / "local-demo"
    metadata_path = _write_local_module_project(project_root)

    register_module(
        ModuleRegisterRequest(
            app_dir=app_dir,
            module="local-demo",
            metadata=metadata_path,
            project="local-demo-proj",
            project_local_path=project_root,
        )
    )

    add_module(app_dir, "local-demo")

    cfg = _load_yaml(app_dir / "nsx.yml")
    assert [item["name"] for item in cfg["modules"]] == ["local-demo"]
    vendored_readme = app_dir / "modules" / "local-demo" / "README.md"
    assert vendored_readme.read_text(encoding="utf-8") == "version one\n"

    (project_root / "README.md").write_text("version two\n", encoding="utf-8")
    update_modules(app_dir, module="local-demo")
    assert vendored_readme.read_text(encoding="utf-8") == "version two\n"

    remove_module(app_dir, "local-demo")
    cfg = _load_yaml(app_dir / "nsx.yml")
    assert cfg["modules"] == []
    assert not (app_dir / "modules" / "local-demo").exists()


def test_build_app_uses_shared_impl_and_triggers_configure_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_workspace(WorkspaceInitRequest(workspace=tmp_path, skip_update=True))
    create_app(tmp_path, "hello_build", board="apollo510_evb", no_bootstrap=True)

    app_dir = tmp_path / "apps" / "hello_build"
    build_dir = app_dir / "build" / "apollo510_evb"
    configure_calls: list[tuple[Path, Path, str]] = []
    build_calls: list[list[str]] = []

    def fake_configure(app: Path, build: Path, board: str) -> None:
        configure_calls.append((app, build, board))
        build.mkdir(parents=True, exist_ok=True)
        (build / "build.ninja").write_text("# fake\n", encoding="utf-8")

    def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
        del cwd
        build_calls.append(cmd)

    monkeypatch.setattr(cli, "_run_cmake_configure", fake_configure)
    monkeypatch.setattr(cli, "_run", fake_run)

    build_app(AppBuildRequest(app_dir=app_dir, jobs=3))

    assert configure_calls == [(app_dir, build_dir, "apollo510_evb")]
    assert build_calls == [
        ["cmake", "--build", str(build_dir), "--target", "hello_build", "-j", "3"]
    ]
