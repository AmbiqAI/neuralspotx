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
    ModuleInitRequest,
    ModuleRegisterRequest,
    ModuleUpdateRequest,
    NSXError,
    add_module,
    build_app,
    clean_app,
    configure_app,
    create_app,
    doctor,
    flash_app,
    init_module,
    register_module,
    remove_module,
    update_modules,
    view_app,
)
from neuralspotx.constants import DEFAULT_BOARD


def test_create_app_dispatches_to_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str, str | None, bool, bool]] = []

    def fake_create(
        app_dir: Path,
        *,
        board: str = "apollo510_evb",
        soc: str | None = None,
        force: bool = False,
        no_bootstrap: bool = False,
    ) -> None:
        calls.append((app_dir, board, soc, force, no_bootstrap))

    monkeypatch.setattr(operations, "create_app_impl", fake_create)

    create_app(
        AppCreateRequest(
            app_dir=tmp_path,
            board="apollo4p_evb",
            soc="apollo4p",
            force=True,
            no_bootstrap=True,
        )
    )

    assert calls == [(tmp_path.resolve(), "apollo4p_evb", "apollo4p", True, True)]


def test_create_app_uses_canonical_default_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, str, str | None, bool, bool]] = []

    def fake_create(
        app_dir: Path,
        *,
        board: str = DEFAULT_BOARD,
        soc: str | None = None,
        force: bool = False,
        no_bootstrap: bool = False,
    ) -> None:
        calls.append((app_dir, board, soc, force, no_bootstrap))

    monkeypatch.setattr(operations, "create_app_impl", fake_create)

    create_app(tmp_path)

    assert calls == [(tmp_path.resolve(), DEFAULT_BOARD, None, False, False)]


def test_doctor_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    doctor_calls = 0

    def fake_doctor() -> object:
        nonlocal doctor_calls
        doctor_calls += 1
        from neuralspotx.models import DoctorReport

        return DoctorReport(checks=())

    monkeypatch.setattr(operations, "doctor_impl", fake_doctor)

    doctor()

    assert doctor_calls == 1


def test_configure_view_and_clean_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_calls: list[tuple[Path, str | None, Path | None, str | None, str | None, bool]] = []
    view_calls: list[tuple[Path, str | None, Path | None, str | None, str | None]] = []
    clean_calls: list[tuple[Path, str | None, Path | None, str | None, bool]] = []

    def fake_configure(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        toolchain: str | None = None,
        probe_serial: str | None = None,
        frozen: bool = False,
    ) -> None:
        configure_calls.append((app_dir, board, build_dir, toolchain, probe_serial, frozen))

    def fake_view(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        toolchain: str | None = None,
        probe_serial: str | None = None,
        reset_on_open: bool = True,
        reset_delay_ms: int = 400,
        duration_s: float | None = None,
        capture: Path | None = None,
    ) -> None:
        view_calls.append((app_dir, board, build_dir, toolchain, probe_serial))

    def fake_clean(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        toolchain: str | None = None,
        full: bool = False,
        reset: bool = False,
        force: bool = False,
    ) -> None:
        clean_calls.append((app_dir, board, build_dir, toolchain, full))

    monkeypatch.setattr(operations, "configure_app_impl", fake_configure)
    monkeypatch.setattr(operations, "view_app_impl", fake_view)
    monkeypatch.setattr(operations, "clean_app_impl", fake_clean)

    app_dir = tmp_path / "app"
    build_dir = tmp_path / "build"

    configure_app(
        AppActionRequest(
            app_dir=app_dir,
            board="apollo510_evb",
            build_dir=build_dir,
            probe_serial="1160002204",
            frozen=True,
        )
    )
    view_app(app_dir, board="apollo3p_evb", build_dir=build_dir, probe_serial="1160002204")
    clean_app(AppCleanRequest(app_dir=app_dir, build_dir=build_dir, full=True))

    assert configure_calls == [
        (app_dir.resolve(), "apollo510_evb", build_dir.resolve(), None, "1160002204", True)
    ]
    assert view_calls == [
        (app_dir.resolve(), "apollo3p_evb", build_dir.resolve(), None, "1160002204")
    ]
    assert clean_calls == [(app_dir.resolve(), None, build_dir.resolve(), None, True)]


def test_build_and_flash_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_calls: list[tuple[Path, str | None, Path | None, str | None, str | None, int, bool]] = []
    flash_calls: list[tuple[Path, str | None, Path | None, str | None, str | None, int, bool]] = []

    def fake_build(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        toolchain: str | None = None,
        target: str | None = None,
        jobs: int = 8,
        frozen: bool = False,
        on_line: object = None,
    ) -> None:
        build_calls.append((app_dir, board, build_dir, toolchain, target, jobs, frozen))

    def fake_flash(
        app_dir: Path,
        *,
        board: str | None = None,
        build_dir: Path | None = None,
        toolchain: str | None = None,
        probe_serial: str | None = None,
        jobs: int = 8,
        frozen: bool = False,
        on_line: object = None,
    ) -> None:
        flash_calls.append((app_dir, board, build_dir, toolchain, probe_serial, jobs, frozen))

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
            frozen=True,
        )
    )
    flash_app(
        AppFlashRequest(
            app_dir=app_dir, build_dir=build_dir, probe_serial="1160002204", jobs=2, frozen=True
        )
    )

    assert build_calls == [
        (app_dir.resolve(), "apollo4l_evb", build_dir.resolve(), None, "custom-target", 3, True)
    ]
    assert flash_calls == [
        (app_dir.resolve(), None, build_dir.resolve(), None, "1160002204", 2, True)
    ]


def test_module_change_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    add_calls: list[tuple[Path, str, bool]] = []
    remove_calls: list[tuple[Path, str, bool]] = []
    update_calls: list[tuple[Path, str | None, bool]] = []

    def fake_add(
        app_dir: Path,
        module: str,
        *,
        local: bool = False,
        vendored: bool = False,
        path: str | None = None,
        boards: tuple[str, ...] = (),
        dry_run: bool = False,
    ) -> None:
        add_calls.append((app_dir, module, dry_run))

    def fake_remove(app_dir: Path, module: str, *, dry_run: bool = False) -> None:
        remove_calls.append((app_dir, module, dry_run))

    def fake_update(
        app_dir: Path,
        *,
        module_name: str | None = None,
        dry_run: bool = False,
    ) -> None:
        update_calls.append((app_dir, module_name, dry_run))

    monkeypatch.setattr(operations, "add_module_impl", fake_add)
    monkeypatch.setattr(operations, "remove_module_impl", fake_remove)
    monkeypatch.setattr(operations, "update_modules_impl", fake_update)

    app_dir = tmp_path / "app"

    add_module(ModuleChangeRequest(app_dir=app_dir, module="nsx-uart", dry_run=True))
    remove_module(app_dir, "nsx-uart", dry_run=True)
    update_modules(ModuleUpdateRequest(app_dir=app_dir, module="nsx-uart"))

    assert add_calls == [(app_dir.resolve(), "nsx-uart", True)]
    assert remove_calls == [(app_dir.resolve(), "nsx-uart", True)]
    assert update_calls == [(app_dir.resolve(), "nsx-uart", False)]


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
    ) -> None:
        calls.append((
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
        ))

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
        )
    ]


def test_module_init_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[ModuleInitRequest] = []

    def fake_init(request: ModuleInitRequest) -> None:
        calls.append(request)

    monkeypatch.setattr(operations, "init_module_impl", fake_init)

    module_dir = tmp_path / "my-module"
    init_module(
        ModuleInitRequest(
            module_dir=module_dir,
            module_name="my-module",
            module_type="backend_specific",
            summary="Generated test module",
            version="0.2.0",
            dependencies=["nsx-core", "nsx-i2c"],
            boards=["*"],
            socs=["apollo510"],
            toolchains=["arm-none-eabi-gcc"],
            force=True,
        )
    )

    assert len(calls) == 1
    request = calls[0]
    assert request.module_dir == module_dir
    assert request.module_name == "my-module"
    assert request.module_type == "backend_specific"
    assert request.summary == "Generated test module"
    assert request.version == "0.2.0"
    assert request.dependencies == ["nsx-core", "nsx-i2c"]
    assert request.boards == ["*"]
    assert request.socs == ["apollo510"]
    assert request.toolchains == ["arm-none-eabi-gcc"]
    assert request.force is True


def test_module_api_validates_required_fields(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="add_module requires a module name"):
        add_module(tmp_path, "")

    with pytest.raises(NSXError, match="remove_module requires a module name"):
        remove_module(tmp_path, "")

    with pytest.raises(NSXError, match="register_module requires module, metadata, and project"):
        register_module(tmp_path, "")
