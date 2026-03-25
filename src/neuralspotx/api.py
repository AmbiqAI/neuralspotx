"""Programmatic API for the NSX workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import operations

PathLike = str | Path


class NSXError(RuntimeError):
    """Raised when an NSX workflow operation fails."""


@dataclass(slots=True)
class WorkspaceInitRequest:
    workspace: PathLike
    nsx_repo_url: str | None = None
    nsx_revision: str = "main"
    ambiqsuite_repo_url: str | None = None
    ambiqsuite_revision: str = "main"
    skip_update: bool = False


@dataclass(slots=True)
class AppCreateRequest:
    workspace: PathLike
    name: str
    board: str = "apollo510_evb"
    soc: str | None = None
    force: bool = False
    init_workspace: bool = False
    no_bootstrap: bool = False
    no_sync: bool = False


@dataclass(slots=True)
class WorkspaceSyncRequest:
    workspace: PathLike


@dataclass(slots=True)
class AppActionRequest:
    app_dir: PathLike
    board: str | None = None
    build_dir: PathLike | None = None


@dataclass(slots=True)
class AppBuildRequest(AppActionRequest):
    target: str | None = None
    jobs: int = 8


@dataclass(slots=True)
class AppFlashRequest(AppActionRequest):
    jobs: int = 8


@dataclass(slots=True)
class AppCleanRequest(AppActionRequest):
    full: bool = False


@dataclass(slots=True)
class ModuleChangeRequest:
    app_dir: PathLike
    module: str
    dry_run: bool = False
    no_sync: bool = False


@dataclass(slots=True)
class ModuleUpdateRequest:
    app_dir: PathLike
    module: str | None = None
    dry_run: bool = False
    no_sync: bool = False


@dataclass(slots=True)
class ModuleRegisterRequest:
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
    no_sync: bool = False


def _invoke(func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except SystemExit as exc:
        code = exc.code
        if code in (None, 0):
            return
        raise NSXError(str(code)) from None


def init_workspace(
    workspace: PathLike | WorkspaceInitRequest,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    request = (
        workspace
        if isinstance(workspace, WorkspaceInitRequest)
        else WorkspaceInitRequest(
            workspace=workspace,
            nsx_repo_url=nsx_repo_url,
            nsx_revision=nsx_revision,
            ambiqsuite_repo_url=ambiqsuite_repo_url,
            ambiqsuite_revision=ambiqsuite_revision,
            skip_update=skip_update,
        )
    )
    _invoke(
        operations.init_workspace_impl,
        Path(request.workspace).expanduser().resolve(),
        nsx_repo_url=request.nsx_repo_url,
        nsx_revision=request.nsx_revision,
        ambiqsuite_repo_url=request.ambiqsuite_repo_url,
        ambiqsuite_revision=request.ambiqsuite_revision,
        skip_update=request.skip_update,
    )


def create_app(
    workspace: PathLike | AppCreateRequest,
    name: str | None = None,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    init_workspace: bool = False,
    no_bootstrap: bool = False,
    no_sync: bool = False,
) -> None:
    request = (
        workspace
        if isinstance(workspace, AppCreateRequest)
        else AppCreateRequest(
            workspace=workspace,
            name=name or "",
            board=board,
            soc=soc,
            force=force,
            init_workspace=init_workspace,
            no_bootstrap=no_bootstrap,
            no_sync=no_sync,
        )
    )
    if not request.name:
        raise NSXError("create_app requires a non-empty app name")
    _invoke(
        operations.create_app_impl,
        Path(request.workspace).expanduser().resolve(),
        request.name,
        board=request.board,
        soc=request.soc,
        force=request.force,
        init_workspace=request.init_workspace,
        no_bootstrap=request.no_bootstrap,
        no_sync=request.no_sync,
    )


def sync_workspace(workspace: PathLike | WorkspaceSyncRequest) -> None:
    request = (
        workspace
        if isinstance(workspace, WorkspaceSyncRequest)
        else WorkspaceSyncRequest(workspace=workspace)
    )
    _invoke(operations.sync_workspace_impl, Path(request.workspace).expanduser().resolve())


def doctor() -> None:
    _invoke(operations.doctor_impl)


def configure_app(
    app_dir: PathLike | AppActionRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
) -> None:
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
    no_sync: bool = False,
) -> None:
    request = (
        app_dir
        if isinstance(app_dir, ModuleChangeRequest)
        else ModuleChangeRequest(
            app_dir=app_dir,
            module=module or "",
            dry_run=dry_run,
            no_sync=no_sync,
        )
    )
    if not request.module:
        raise NSXError("add_module requires a module name")
    _invoke(
        operations.add_module_impl,
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        dry_run=request.dry_run,
        no_sync=request.no_sync,
    )


def remove_module(
    app_dir: PathLike | ModuleChangeRequest,
    module: str | None = None,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    request = (
        app_dir
        if isinstance(app_dir, ModuleChangeRequest)
        else ModuleChangeRequest(
            app_dir=app_dir,
            module=module or "",
            dry_run=dry_run,
            no_sync=no_sync,
        )
    )
    if not request.module:
        raise NSXError("remove_module requires a module name")
    _invoke(
        operations.remove_module_impl,
        Path(request.app_dir).expanduser().resolve(),
        request.module,
        dry_run=request.dry_run,
        no_sync=request.no_sync,
    )


def update_modules(
    app_dir: PathLike | ModuleUpdateRequest,
    *,
    module: str | None = None,
    dry_run: bool = False,
    no_sync: bool = False,
) -> None:
    request = (
        app_dir
        if isinstance(app_dir, ModuleUpdateRequest)
        else ModuleUpdateRequest(
            app_dir=app_dir,
            module=module,
            dry_run=dry_run,
            no_sync=no_sync,
        )
    )
    _invoke(
        operations.update_modules_impl,
        Path(request.app_dir).expanduser().resolve(),
        module_name=request.module,
        dry_run=request.dry_run,
        no_sync=request.no_sync,
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
    no_sync: bool = False,
) -> None:
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
            no_sync=no_sync,
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
        no_sync=request.no_sync,
    )
