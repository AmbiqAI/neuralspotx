"""Programmatic API for the NSX workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import module_discovery, operations, project_config
from .metadata import load_yaml, validate_nsx_module_metadata

PathLike = str | Path


class NSXError(RuntimeError):
    """Raised when an NSX workflow operation fails."""


@dataclass(slots=True)
class AppCreateRequest:
    """Request parameters for creating a new NSX app.

    Attributes:
        app_dir: Target app root.
        board: Target board identifier.
        soc: Optional SoC override. When omitted, NSX infers it from ``board``.
        force: Allow writing into a non-empty app directory.
        no_bootstrap: Skip starter-module initialization.
    """

    app_dir: PathLike
    board: str = "apollo510_evb"
    soc: str | None = None
    force: bool = False
    no_bootstrap: bool = False


@dataclass(slots=True)
class AppActionRequest:
    """Base request for app-scoped actions.

    Attributes:
        app_dir: App directory containing ``nsx.yml``.
        board: Optional board override.
        build_dir: Optional build directory override.
    """

    app_dir: PathLike
    board: str | None = None
    build_dir: PathLike | None = None


@dataclass(slots=True)
class AppBuildRequest(AppActionRequest):
    """Request parameters for building an app."""

    target: str | None = None
    jobs: int = 8


@dataclass(slots=True)
class AppFlashRequest(AppActionRequest):
    """Request parameters for flashing an app."""

    jobs: int = 8


@dataclass(slots=True)
class AppCleanRequest(AppActionRequest):
    """Request parameters for cleaning an app build."""

    full: bool = False


@dataclass(slots=True)
class ModuleChangeRequest:
    """Request parameters for adding or removing a module."""

    app_dir: PathLike
    module: str
    dry_run: bool = False


@dataclass(slots=True)
class ModuleUpdateRequest:
    """Request parameters for updating one or more modules."""

    app_dir: PathLike
    module: str | None = None
    dry_run: bool = False


@dataclass(slots=True)
class ModuleRegisterRequest:
    """Request parameters for registering an app-local module override."""

    app_dir: PathLike
    module: str
    metadata: PathLike
    project: str
    project_url: str | None = None
    project_revision: str | None = None
    project_path: str | None = None
    project_local_path: PathLike | None = None
    override: bool = False
    dry_run: bool = False


def _invoke(func, *args, **kwargs) -> None:
    """Invoke an NSX operation and normalize ``SystemExit`` into ``NSXError``."""

    try:
        func(*args, **kwargs)
    except SystemExit as exc:
        code = exc.code
        if code in (None, 0):
            return
        raise NSXError(str(code)) from None


def create_app(
    app_dir: PathLike | AppCreateRequest,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    no_bootstrap: bool = False,
) -> None:
    """Create a new NSX app project.

    Args:
        app_dir: Either an app-root path or a typed request object.
        board: Target board identifier.
        soc: Optional SoC override.
        force: Allow writing into a non-empty app directory.
        no_bootstrap: Skip starter-module initialization.
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
    _invoke(
        operations.create_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        soc=request.soc,
        force=request.force,
        no_bootstrap=request.no_bootstrap,
    )


def doctor() -> None:
    """Run the NSX environment diagnostics."""

    _invoke(operations.doctor_impl)


def configure_app(
    app_dir: PathLike | AppActionRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
) -> None:
    """Configure an app build directory with CMake."""

    request = (
        app_dir
        if isinstance(app_dir, AppActionRequest)
        else AppActionRequest(app_dir=app_dir, board=board, build_dir=build_dir)
    )
    _invoke(
        operations.configure_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
    )


def build_app(
    app_dir: PathLike | AppBuildRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    target: str | None = None,
    jobs: int = 8,
) -> None:
    """Build an NSX app."""

    request = (
        app_dir
        if isinstance(app_dir, AppBuildRequest)
        else AppBuildRequest(
            app_dir=app_dir,
            board=board,
            build_dir=build_dir,
            target=target,
            jobs=jobs,
        )
    )
    _invoke(
        operations.build_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
        target=request.target,
        jobs=request.jobs,
    )


def flash_app(
    app_dir: PathLike | AppFlashRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    jobs: int = 8,
) -> None:
    """Build and flash an NSX app."""

    request = (
        app_dir
        if isinstance(app_dir, AppFlashRequest)
        else AppFlashRequest(app_dir=app_dir, board=board, build_dir=build_dir, jobs=jobs)
    )
    _invoke(
        operations.flash_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
        jobs=request.jobs,
    )


def view_app(
    app_dir: PathLike | AppActionRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
) -> None:
    """Launch the SEGGER SWO viewer for an app."""

    request = (
        app_dir
        if isinstance(app_dir, AppActionRequest)
        else AppActionRequest(app_dir=app_dir, board=board, build_dir=build_dir)
    )
    _invoke(
        operations.view_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
    )


def clean_app(
    app_dir: PathLike | AppCleanRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    full: bool = False,
) -> None:
    """Clean or fully remove an app build directory."""

    request = (
        app_dir
        if isinstance(app_dir, AppCleanRequest)
        else AppCleanRequest(app_dir=app_dir, board=board, build_dir=build_dir, full=full)
    )
    _invoke(
        operations.clean_app_impl,
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
        full=request.full,
    )


def add_module(
    app_dir: PathLike | ModuleChangeRequest,
    module: str | None = None,
    *,
    dry_run: bool = False,
) -> None:
    """Add a module to an app."""

    request = (
        app_dir
        if isinstance(app_dir, ModuleChangeRequest)
        else ModuleChangeRequest(
            app_dir=app_dir,
            module=module or "",
            dry_run=dry_run,
        )
    )
    if not request.module:
        raise NSXError("add_module requires a module name")
    _invoke(
        operations.add_module_impl,
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        dry_run=request.dry_run,
    )


def remove_module(
    app_dir: PathLike | ModuleChangeRequest,
    module: str | None = None,
    *,
    dry_run: bool = False,
) -> None:
    """Remove a module from an app."""

    request = (
        app_dir
        if isinstance(app_dir, ModuleChangeRequest)
        else ModuleChangeRequest(
            app_dir=app_dir,
            module=module or "",
            dry_run=dry_run,
        )
    )
    if not request.module:
        raise NSXError("remove_module requires a module name")
    _invoke(
        operations.remove_module_impl,
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        dry_run=request.dry_run,
    )


def update_modules(
    app_dir: PathLike | ModuleUpdateRequest,
    *,
    module: str | None = None,
    dry_run: bool = False,
) -> None:
    """Refresh one or more enabled modules from the registry."""

    request = (
        app_dir
        if isinstance(app_dir, ModuleUpdateRequest)
        else ModuleUpdateRequest(
            app_dir=app_dir,
            module=module,
            dry_run=dry_run,
        )
    )
    _invoke(
        operations.update_modules_impl,
        Path(request.app_dir).expanduser().resolve(),
        module_name=request.module,
        dry_run=request.dry_run,
    )


def register_module(
    app_dir: PathLike | ModuleRegisterRequest,
    module: str | None = None,
    *,
    metadata: PathLike | None = None,
    project: str | None = None,
    project_url: str | None = None,
    project_revision: str | None = None,
    project_path: str | None = None,
    project_local_path: PathLike | None = None,
    override: bool = False,
    dry_run: bool = False,
) -> None:
    """Register an app-local module override."""

    request = (
        app_dir
        if isinstance(app_dir, ModuleRegisterRequest)
        else ModuleRegisterRequest(
            app_dir=app_dir,
            module=module or "",
            metadata=metadata or "",
            project=project or "",
            project_url=project_url,
            project_revision=project_revision,
            project_path=project_path,
            project_local_path=project_local_path,
            override=override,
            dry_run=dry_run,
        )
    )
    if not request.module or not request.metadata or not request.project:
        raise NSXError("register_module requires module, metadata, and project")
    _invoke(
        operations.register_module_impl,
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        metadata=Path(request.metadata).expanduser(),
        project=request.project,
        project_url=request.project_url,
        project_revision=request.project_revision,
        project_path=request.project_path,
        project_local_path=(
            Path(request.project_local_path).expanduser() if request.project_local_path else None
        ),
        override=request.override,
        dry_run=request.dry_run,
    )


def validate_module_metadata(
    metadata: PathLike,
) -> dict[str, Any]:
    """Validate an ``nsx-module.yaml`` file and return the parsed data.

    Raises ``NSXError`` when the file is missing, malformed, or fails
    required-field checks.
    """

    path = Path(metadata).expanduser().resolve()
    try:
        data = load_yaml(path)
        validate_nsx_module_metadata(data, str(path))
    except (ValueError, SystemExit) as exc:
        raise NSXError(str(exc)) from None
    return data


def find_app_root(start: PathLike | None = None) -> Path | None:
    """Find the nearest app root containing ``nsx.yml``."""

    return project_config.find_app_root(
        Path(start).expanduser().resolve() if start is not None else None
    )


def resolve_app_dir(explicit: PathLike | None) -> Path:
    """Resolve an app directory from an explicit path or upward search."""

    return project_config.resolve_app_dir(explicit)


def list_modules(
    *,
    app_dir: PathLike | None = None,
    registry_only: bool = False,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """List available modules from the effective registry context."""

    return module_discovery.list_modules(
        app_dir=Path(app_dir).expanduser().resolve() if app_dir is not None else None,
        registry_only=registry_only,
        include_metadata=include_metadata,
    )


def describe_module(
    module: str,
    *,
    app_dir: PathLike | None = None,
) -> dict[str, Any]:
    """Describe a single module from the effective registry context."""

    return module_discovery.describe_module(
        module,
        app_dir=Path(app_dir).expanduser().resolve() if app_dir is not None else None,
    )


def search_modules(
    query: str,
    *,
    app_dir: PathLike | None = None,
    board: str | None = None,
    soc: str | None = None,
    toolchain: str | None = None,
    include_incompatible: bool = False,
) -> list[dict[str, Any]]:
    """Search modules by keyword and target compatibility context."""

    return module_discovery.search_modules(
        query,
        app_dir=Path(app_dir).expanduser().resolve() if app_dir is not None else None,
        board=board,
        soc=soc,
        toolchain=toolchain,
        include_incompatible=include_incompatible,
    )
