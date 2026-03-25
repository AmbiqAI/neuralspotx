from __future__ import annotations

from pathlib import Path

import pytest

import neuralspotx.operations as operations
from neuralspotx import (
    AppActionRequest,
    AppBuildRequest,
    AppCleanRequest,
    AppCreateRequest,
    AppFlashRequest,
    ModuleChangeRequest,
    ModuleRegisterRequest,
    ModuleUpdateRequest,
    NSXError,
    WorkspaceInitRequest,
    WorkspaceSyncRequest,
    add_module,
    build_app,
    clean_app,
    configure_app,
    create_app,
    doctor,
    flash_app,
    init_workspace,
    register_module,
    remove_module,
    sync_workspace,
    update_modules,
    view_app,
)


def test_invoke_wraps_nonzero_system_exit() -> None:
    def fail() -> None:
        raise SystemExit("boom")

    with pytest.raises(NSXError, match="boom"):
        from neuralspotx.api import _invoke

        _invoke(fail)


def test_init_workspace_dispatches_to_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, str | None, str, str | None, str, bool]] = []

    def fake_init(
        workspace: Path,
        *,
        nsx_repo_url: str | None = None,
        nsx_revision: str = "main",
        ambiqsuite_repo_url: str | None = None,
        ambiqsuite_revision: str = "main",
        skip_update: bool = False,
    ) -> None:
        calls.append(
            (
                workspace,
                nsx_repo_url,
                nsx_revision,
                ambiqsuite_repo_url,
                ambiqsuite_revision,
                skip_update,
            )
        )

    monkeypatch.setattr(operations, "init_workspace_impl", fake_init)

    init_workspace(
        WorkspaceInitRequest(
            workspace=tmp_path,
            nsx_repo_url="https://example.com/nsx.git",
            nsx_revision="feature",
            ambiqsuite_repo_url="https://example.com/ambiq.git",
            ambiqsuite_revision="sdk-tag",
            skip_update=True,
        )
    )

    assert calls == [
        (
            tmp_path.resolve(),
            "https://example.com/nsx.git",
            "feature",
            "https://example.com/ambiq.git",
            "sdk-tag",
            True,
        )
    ]


def test_create_app_dispatches_to_operations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path, str, str, str | None, bool, bool, bool, bool]] = []

    def fake_create(
        workspace: Path,
        name: str,
        *,
        board: str = "apollo510_evb",
        soc: str | None = None,
        force: bool = False,
        init_workspace: bool = False,
        no_bootstrap: bool = False,
        no_sync: bool = False,
    ) -> None:
        calls.append((workspace, name, board, soc, force, init_workspace, no_bootstrap, no_sync))

    monkeypatch.setattr(operations, "create_app_impl", fake_create)

    create_app(
        AppCreateRequest(
            workspace=tmp_path,
            name="hello",
            board="apollo4p_evb",
            soc="apollo4p",
            force=True,
            init_workspace=True,
            no_bootstrap=True,
            no_sync=True,
        )
    )

    assert calls == [
        (tmp_path.resolve(), "hello", "apollo4p_evb", "apollo4p", True, True, True, True)
    ]


def test_create_app_requires_nonempty_name(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="non-empty app name"):
        create_app(tmp_path, "")


def test_sync_and_doctor_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sync_calls: list[Path] = []
    doctor_calls = 0

    def fake_sync(workspace: Path) -> None:
        sync_calls.append(workspace)

    def fake_doctor() -> None:
        nonlocal doctor_calls
        doctor_calls += 1

    monkeypatch.setattr(operations, "sync_workspace_impl", fake_sync)
    monkeypatch.setattr(operations, "doctor_impl", fake_doctor)

    sync_workspace(WorkspaceSyncRequest(workspace=tmp_path))
    doctor()

    assert sync_calls == [tmp_path.resolve()]
    assert doctor_calls == 1


def test_configure_view_and_clean_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_calls: list[tuple[Path, str | None, Path | None]] = []
    view_calls: list[tuple[Path, str | None, Path | None]] = []
    clean_calls: list[tuple[Path, str | None, Path | None, bool]] = []

    def fake_configure(app_dir: Path, *, board: str | None = None, build_dir: Path | None = None) -> None:
        configure_calls.append((app_dir, board, build_dir))

    def fake_view(app_dir: Path, *, board: str | None = None, build_dir: Path | None = None) -> None:
        view_calls.append((app_dir, board, build_dir))

    def fake_clean(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        full: bool = False,
    ) -> None:
        clean_calls.append((app_dir, board, build_dir, full))

    monkeypatch.setattr(operations, "configure_app_impl", fake_configure)
    monkeypatch.setattr(operations, "view_app_impl", fake_view)
    monkeypatch.setattr(operations, "clean_app_impl", fake_clean)

    app_dir = tmp_path / "app"
    build_dir = tmp_path / "build"

    configure_app(AppActionRequest(app_dir=app_dir, board="apollo510_evb", build_dir=build_dir))
    view_app(app_dir, board="apollo3p_evb", build_dir=build_dir)
    clean_app(AppCleanRequest(app_dir=app_dir, build_dir=build_dir, full=True))

    assert configure_calls == [(app_dir.resolve(), "apollo510_evb", build_dir.resolve())]
    assert view_calls == [(app_dir.resolve(), "apollo3p_evb", build_dir.resolve())]
    assert clean_calls == [(app_dir.resolve(), None, build_dir.resolve(), True)]


def test_build_and_flash_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_calls: list[tuple[Path, str | None, Path | None, str | None, int]] = []
    flash_calls: list[tuple[Path, str | None, Path | None, int]] = []

    def fake_build(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        target: str | None = None,
        jobs: int = 8,
    ) -> None:
        build_calls.append((app_dir, board, build_dir, target, jobs))

    def fake_flash(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        jobs: int = 8,
    ) -> None:
        flash_calls.append((app_dir, board, build_dir, jobs))

    monkeypatch.setattr(operations, "build_app_impl", fake_build)
    monkeypatch.setattr(operations, "flash_app_impl", fake_flash)

    app_dir = tmp_path / "app"
    build_dir = tmp_path / "build"

    build_app(
        AppBuildRequest(
            app_dir=app_dir,
            board="apollo4l_evb",
            build_dir=build_dir,
            target="custom-target",
            jobs=3,
        )
    )
    flash_app(AppFlashRequest(app_dir=app_dir, build_dir=build_dir, jobs=2))

    assert build_calls == [
        (app_dir.resolve(), "apollo4l_evb", build_dir.resolve(), "custom-target", 3)
    ]
    assert flash_calls == [(app_dir.resolve(), None, build_dir.resolve(), 2)]


def test_module_change_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add_calls: list[tuple[Path, str, bool, bool]] = []
    remove_calls: list[tuple[Path, str, bool, bool]] = []
    update_calls: list[tuple[Path, str | None, bool, bool]] = []

    def fake_add(app_dir: Path, module: str, *, dry_run: bool = False, no_sync: bool = False) -> None:
        add_calls.append((app_dir, module, dry_run, no_sync))

    def fake_remove(
        app_dir: Path, module: str, *, dry_run: bool = False, no_sync: bool = False
    ) -> None:
        remove_calls.append((app_dir, module, dry_run, no_sync))

    def fake_update(
        app_dir: Path,
        *,
        module_name: str | None = None,
        dry_run: bool = False,
        no_sync: bool = False,
    ) -> None:
        update_calls.append((app_dir, module_name, dry_run, no_sync))

    monkeypatch.setattr(operations, "add_module_impl", fake_add)
    monkeypatch.setattr(operations, "remove_module_impl", fake_remove)
    monkeypatch.setattr(operations, "update_modules_impl", fake_update)

    app_dir = tmp_path / "app"

    add_module(ModuleChangeRequest(app_dir=app_dir, module="nsx-uart", dry_run=True, no_sync=True))
    remove_module(app_dir, "nsx-uart", dry_run=True)
    update_modules(ModuleUpdateRequest(app_dir=app_dir, module="nsx-uart", no_sync=True))

    assert add_calls == [(app_dir.resolve(), "nsx-uart", True, True)]
    assert remove_calls == [(app_dir.resolve(), "nsx-uart", True, False)]
    assert update_calls == [(app_dir.resolve(), "nsx-uart", False, True)]


def test_module_register_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[
        tuple[
            Path,
            str,
            Path,
            str,
            str | None,
            str | None,
            str | None,
            Path | None,
            bool,
            bool,
            bool,
        ]
    ] = []

    def fake_register(
        app_dir: Path,
        module: str,
        *,
        metadata: Path,
        project: str,
        project_url: str | None = None,
        project_revision: str | None = None,
        project_path: str | None = None,
        project_local_path: Path | None = None,
        override: bool = False,
        dry_run: bool = False,
        no_sync: bool = False,
    ) -> None:
        calls.append(
            (
                app_dir,
                module,
                metadata,
                project,
                project_url,
                project_revision,
                project_path,
                project_local_path,
                override,
                dry_run,
                no_sync,
            )
        )

    monkeypatch.setattr(operations, "register_module_impl", fake_register)

    app_dir = tmp_path / "app"
    metadata = tmp_path / "nsx-module.yaml"
    project_local_path = tmp_path / "module-project"

    register_module(
        ModuleRegisterRequest(
            app_dir=app_dir,
            module="local-demo",
            metadata=metadata,
            project="local-demo-proj",
            project_url="https://example.com/module.git",
            project_revision="main",
            project_path="modules/local-demo",
            project_local_path=project_local_path,
            override=True,
            dry_run=True,
            no_sync=True,
        )
    )

    assert calls == [
        (
            app_dir.resolve(),
            "local-demo",
            metadata.expanduser(),
            "local-demo-proj",
            "https://example.com/module.git",
            "main",
            "modules/local-demo",
            project_local_path.expanduser(),
            True,
            True,
            True,
        )
    ]


def test_module_api_validates_required_fields(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="add_module requires a module name"):
        add_module(tmp_path, "")

    with pytest.raises(NSXError, match="remove_module requires a module name"):
        remove_module(tmp_path, "")

    with pytest.raises(NSXError, match="register_module requires module, metadata, and project"):
        register_module(tmp_path, "")
