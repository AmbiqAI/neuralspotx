from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from neuralspotx import (
    AppCleanRequest,
    AppCreateRequest,
    ModuleRegisterRequest,
    NSXError,
    WorkspaceInitRequest,
    clean_app,
    create_app,
    init_workspace,
    register_module,
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


def test_create_app_requires_initialized_workspace(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="Workspace is not initialized"):
        create_app(tmp_path, "hello_fail", board="apollo510_evb", no_bootstrap=True)


def test_create_app_can_initialize_workspace(tmp_path: Path) -> None:
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
