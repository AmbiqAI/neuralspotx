"""Module-scoped operations: add, remove, update, register, init, validate, list, describe, search."""

from __future__ import annotations

from pathlib import Path

from .. import module_discovery, operations, project_config
from .._errors import NSXConfigError, NSXError, NSXModuleError
from ..metadata import load_yaml, validate_nsx_module_metadata
from ..models import DiscoveryRecord, ModuleChange, SearchResult
from ._requests import (
    ModuleChangeRequest,
    ModuleInitRequest,
    ModuleRegisterRequest,
    ModuleUpdateRequest,
)

PathLike = str | Path


def add_module(
    app_dir: PathLike | ModuleChangeRequest,
    module: str | None = None,
    *,
    dry_run: bool = False,
    local: bool = False,
    vendored: bool = False,
) -> list[ModuleChange]:
    """Add a module to an app."""

    request = (
        app_dir
        if isinstance(app_dir, ModuleChangeRequest)
        else ModuleChangeRequest(
            app_dir=app_dir,
            module=module or "",
            dry_run=dry_run,
            local=local,
            vendored=vendored,
        )
    )
    if not request.module:
        raise NSXModuleError("add_module requires a module name")
    return operations.add_module_impl(
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        local=request.local,
        vendored=request.vendored,
        dry_run=request.dry_run,
    )


def remove_module(
    app_dir: PathLike | ModuleChangeRequest,
    module: str | None = None,
    *,
    dry_run: bool = False,
) -> list[ModuleChange]:
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
        raise NSXModuleError("remove_module requires a module name")
    return operations.remove_module_impl(
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        dry_run=request.dry_run,
    )


def update_modules(
    app_dir: PathLike | ModuleUpdateRequest,
    *,
    module: str | None = None,
    dry_run: bool = False,
) -> list[ModuleChange]:
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
    return operations.update_modules_impl(
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
) -> ModuleChange:
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
        raise NSXModuleError("register_module requires module, metadata, and project")
    return operations.register_module_impl(
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


def init_module(
    module_dir: PathLike | ModuleInitRequest,
    *,
    module_name: str | None = None,
    module_type: str = "runtime",
    summary: str | None = None,
    version: str = "0.1.0",
    dependencies: list[str] | None = None,
    boards: list[str] | None = None,
    socs: list[str] | None = None,
    toolchains: list[str] | None = None,
    force: bool = False,
) -> ModuleChange:
    """Create a standard custom-module skeleton on disk."""

    request = (
        module_dir
        if isinstance(module_dir, ModuleInitRequest)
        else ModuleInitRequest(
            module_dir=module_dir,
            module_name=module_name,
            module_type=module_type,
            summary=summary,
            version=version,
            dependencies=dependencies,
            boards=boards,
            socs=socs,
            toolchains=toolchains,
            force=force,
        )
    )
    return operations.init_module_impl(
        Path(request.module_dir).expanduser().resolve(),
        module_name=request.module_name,
        module_type=request.module_type,
        summary=request.summary,
        version=request.version,
        dependencies=request.dependencies,
        boards=request.boards,
        socs=request.socs,
        toolchains=request.toolchains,
        force=request.force,
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
    except NSXError:
        raise
    except ValueError as exc:
        raise NSXConfigError(str(exc)) from None
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
) -> list[DiscoveryRecord]:
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
) -> DiscoveryRecord:
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
) -> list[SearchResult]:
    """Search modules by keyword and target compatibility context."""

    return module_discovery.search_modules(
        query,
        app_dir=Path(app_dir).expanduser().resolve() if app_dir is not None else None,
        board=board,
        soc=soc,
        toolchain=toolchain,
        include_incompatible=include_incompatible,
    )
