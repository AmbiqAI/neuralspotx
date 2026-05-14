"""App-scoped operations: create, doctor, configure, build, flash, view, clean."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import operations
from .._io import Emitter, using_emitter
from ..models import DoctorReport
from ..subprocess_utils import timeout_budget
from ._requests import (
    AppActionRequest,
    AppBuildRequest,
    AppCleanRequest,
    AppCreateRequest,
    AppFlashRequest,
    AppViewRequest,
)

PathLike = str | Path


def create_app(
    app_dir: PathLike | AppCreateRequest,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    no_bootstrap: bool = False,
    emit: Emitter | None = None,
) -> Path:
    """Create a new NSX app project.

    Args:
        app_dir: Either an app-root path or a typed request object.
        board: Target board identifier.
        soc: Optional SoC override.
        force: Allow writing into a non-empty app directory.
        no_bootstrap: Skip starter-module initialization.

    Returns:
        The resolved app-root :class:`pathlib.Path`. Suitable for
        chaining into :func:`configure_app`, :func:`build_app`, etc.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppCreateRequest)
        else AppCreateRequest(
            app_dir=app_dir,
            board=board,
            soc=soc,
            force=force,
            no_bootstrap=no_bootstrap,
        )
    )
    with using_emitter(emit):
        return operations.create_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            soc=request.soc,
            force=request.force,
            no_bootstrap=request.no_bootstrap,
        )


def doctor(*, emit: Emitter | None = None) -> DoctorReport:
    """Run the NSX environment diagnostics.

    Returns the structured :class:`DoctorReport`. Never raises on a
    failed check — embedders are expected to inspect ``report.ok`` and
    decide how to react. The CLI handler raises
    :class:`~neuralspotx._errors.NSXToolchainError` so ``nsx doctor``
    keeps its historic non-zero exit code.
    """

    with using_emitter(emit):
        return operations.doctor_impl()


def configure_app(
    app_dir: PathLike | AppActionRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    timeout_s: float | None = None,
    emit: Emitter | None = None,
) -> None:
    """Configure an app build directory with CMake.

    *timeout_s* sets a wall-clock budget for the underlying ``cmake``
    subprocess; the whole process group is killed on timeout.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppActionRequest)
        else AppActionRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            toolchain=toolchain,
            timeout_s=timeout_s,
        )
    )
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.configure_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
        )


def build_app(
    app_dir: PathLike | AppBuildRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    target: str | None = None,
    jobs: int = 8,
    timeout_s: float | None = None,
    emit: Emitter | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Build an NSX app.

    *timeout_s* sets a wall-clock budget for each underlying
    ``cmake`` / ``ninja`` subprocess; the whole process group is killed
    on timeout.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppBuildRequest)
        else AppBuildRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            toolchain=toolchain,
            target=target,
            jobs=jobs,
            timeout_s=timeout_s,
        )
    )
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.build_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            target=request.target,
            jobs=request.jobs,
            on_line=on_line,
        )


def flash_app(
    app_dir: PathLike | AppFlashRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    jobs: int = 8,
    timeout_s: float | None = None,
    emit: Emitter | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Build and flash an NSX app.

    *timeout_s* sets a wall-clock budget for each underlying ``cmake``
    invocation (including the J-Link flash target); the whole process
    group is killed on timeout so a hung ``JLinkExe`` cannot leak.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppFlashRequest)
        else AppFlashRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            toolchain=toolchain,
            jobs=jobs,
            timeout_s=timeout_s,
        )
    )
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.flash_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            jobs=request.jobs,
            on_line=on_line,
        )


def view_app(
    app_dir: PathLike | AppViewRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    reset_on_open: bool = True,
    reset_delay_ms: int = 400,
    timeout_s: float | None = None,
    emit: Emitter | None = None,
) -> None:
    """Launch the SEGGER SWO viewer for an app."""

    request = (
        app_dir
        if isinstance(app_dir, AppViewRequest)
        else AppViewRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            toolchain=toolchain,
            reset_on_open=reset_on_open,
            reset_delay_ms=reset_delay_ms,
            timeout_s=timeout_s,
        )
    )
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.view_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            reset_on_open=request.reset_on_open,
            reset_delay_ms=request.reset_delay_ms,
        )


def clean_app(
    app_dir: PathLike | AppCleanRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    full: bool = False,
    reset: bool = False,
    force: bool = False,
    timeout_s: float | None = None,
    emit: Emitter | None = None,
) -> None:
    """Clean or fully remove an app build directory.

    *timeout_s* sets a wall-clock budget for the underlying ``cmake``
    clean subprocess; the whole process group is killed on timeout.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppCleanRequest)
        else AppCleanRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            toolchain=toolchain,
            full=full,
            reset=reset,
            force=force,
            timeout_s=timeout_s,
        )
    )
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.clean_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            full=request.full,
            reset=request.reset,
            force=request.force,
        )
