"""Programmatic API for the NSX workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import module_discovery, operations, project_config
from ._errors import (
    NSXConfigError,
    NSXError,
    NSXModuleError,
)
from .metadata import load_yaml, validate_nsx_module_metadata
from .models import (
    CacheCleanResult,
    CacheInfo,
    DiscoveryRecord,
    DoctorReport,
    ModuleChange,
    OutdatedReport,
    SearchResult,
)
from .nsx_lock import NsxLock
from .subprocess_utils import timeout_budget

PathLike = str | Path


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
        toolchain: Optional toolchain override (``gcc``, ``armclang``).
        timeout_s: Per-subprocess wall-clock budget (seconds).  ``None``
            disables the timeout.  When the budget elapses, the entire
            child process group is SIGTERM/SIGKILL'd and
            :class:`NSXError` is raised.

    ``timeout_s`` is keyword-only so subclasses (e.g. :class:`AppBuildRequest`)
    can keep their existing positional argument order.  Construct with
    ``AppBuildRequest(app_dir, target="all", jobs=4, timeout_s=300)``.
    """

    app_dir: PathLike
    board: str | None = None
    build_dir: PathLike | None = None
    toolchain: str | None = None
    timeout_s: float | None = field(default=None, kw_only=True)


@dataclass(slots=True)
class AppViewRequest(AppActionRequest):
    """Request parameters for launching the SWO viewer.

    Attributes:
        reset_on_open: When True (default), reset the target once the
            viewer attaches. Avoids a race where SWO is silent until
            the next reset.
        reset_delay_ms: Delay between attaching the viewer and issuing
            the reset, in milliseconds.
    """

    reset_on_open: bool = True
    reset_delay_ms: int = 400


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
class AppLockRequest:
    """Request parameters for resolving and writing ``nsx.lock``.

    Attributes:
        app_dir: App directory containing ``nsx.yml``.
        update: Re-resolve module constraints to current upstream HEAD/tag.
        modules: When given alongside ``update``, only re-resolve these.
        check: Read-only mode — fail if ``nsx.lock`` would change.
        quiet: Suppress the post-write summary print.
        timeout_s: Per-subprocess wall-clock budget (seconds).
        resolve_ttl_s: Override the resolve-ref cache TTL for this call.
            ``None`` uses the ``NSX_RESOLVE_TTL`` env var (default 300s).
            ``0`` disables caching.
    """

    app_dir: PathLike
    update: bool = False
    modules: list[str] | None = None
    check: bool = False
    quiet: bool = False
    timeout_s: float | None = None
    resolve_ttl_s: float | None = None


@dataclass(slots=True)
class AppSyncRequest:
    """Request parameters for materialising ``modules/`` from ``nsx.lock``.

    Attributes:
        app_dir: App directory containing ``nsx.lock``.
        frozen: Read-only mode — verify content hashes, do not modify.
        force: Re-vendor every module even if content_hash matches.
        timeout_s: Per-subprocess wall-clock budget (seconds).  Applied
            to every individual ``git clone`` / ``git fetch`` invoked
            during the sync.
    """

    app_dir: PathLike
    frozen: bool = False
    force: bool = False
    timeout_s: float | None = None


@dataclass(slots=True)
class AppOutdatedRequest:
    """Request parameters for the ``nsx outdated`` report.

    Attributes:
        app_dir: App directory containing ``nsx.lock``.
        as_json: Emit a machine-readable JSON report instead of a table.
        timeout_s: Per-subprocess wall-clock budget (seconds). Applied
            to each ``git ls-remote`` invoked while comparing locked
            commits to upstream tips. ``None`` disables the timeout.
    """

    app_dir: PathLike
    as_json: bool = False
    timeout_s: float | None = None


@dataclass(slots=True)
class AppUpdateRequest:
    """Request parameters for ``nsx update`` (lock --update + sync).

    Attributes:
        app_dir: App directory containing ``nsx.yml``.
        modules: Optional list of module names to update; ``None`` means all.
        timeout_s: Per-subprocess wall-clock budget (seconds).  Applied
            to every individual ``git`` subprocess invoked during the
            re-resolve and re-vendor phases.
    """

    app_dir: PathLike
    modules: list[str] | None = None
    timeout_s: float | None = None


@dataclass(slots=True)
class ModuleChangeRequest:
    """Request parameters for adding or removing a module."""

    app_dir: PathLike
    module: str
    dry_run: bool = False
    local: bool = False
    vendored: bool = False


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


@dataclass(slots=True)
class ModuleInitRequest:
    """Request parameters for creating a custom-module skeleton."""

    module_dir: PathLike
    module_name: str | None = None
    module_type: str = "runtime"
    summary: str | None = None
    version: str = "0.1.0"
    dependencies: list[str] | None = None
    boards: list[str] | None = None
    socs: list[str] | None = None
    toolchains: list[str] | None = None
    force: bool = False


def create_app(
    app_dir: PathLike | AppCreateRequest,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    no_bootstrap: bool = False,
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
    return operations.create_app_impl(
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        soc=request.soc,
        force=request.force,
        no_bootstrap=request.no_bootstrap,
    )


def doctor() -> DoctorReport:
    """Run the NSX environment diagnostics.

    Returns the structured :class:`DoctorReport`. Never raises on a
    failed check — embedders are expected to inspect ``report.ok`` and
    decide how to react. The CLI handler raises
    :class:`~neuralspotx._errors.NSXToolchainError` so ``nsx doctor``
    keeps its historic non-zero exit code.
    """

    return operations.doctor_impl()


def configure_app(
    app_dir: PathLike | AppActionRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    timeout_s: float | None = None,
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
    with timeout_budget(request.timeout_s):
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
    with timeout_budget(request.timeout_s):
        operations.build_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            target=request.target,
            jobs=request.jobs,
        )


def flash_app(
    app_dir: PathLike | AppFlashRequest,
    *,
    board: str | None = None,
    build_dir: PathLike | None = None,
    toolchain: str | None = None,
    jobs: int = 8,
    timeout_s: float | None = None,
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
    with timeout_budget(request.timeout_s):
        operations.flash_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            jobs=request.jobs,
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
    with timeout_budget(request.timeout_s):
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
    timeout_s: float | None = None,
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
            timeout_s=timeout_s,
        )
    )
    with timeout_budget(request.timeout_s):
        operations.clean_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            board=request.board,
            build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
            toolchain=request.toolchain,
            full=request.full,
        )


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


def lock_app(
    app_dir: PathLike | AppLockRequest,
    *,
    update: bool = False,
    modules: list[str] | None = None,
    check: bool = False,
    quiet: bool = False,
    timeout_s: float | None = None,
    resolve_ttl_s: float | None = None,
) -> NsxLock:
    """Resolve module constraints and write ``nsx.lock``.

    Returns the resolved :class:`~neuralspotx.nsx_lock.NsxLock`. The
    filesystem path to the lock file is available on ``lock.path``.
    *timeout_s* applies per ``git`` / ``git ls-remote`` subprocess.
    *resolve_ttl_s* overrides the ``NSX_RESOLVE_TTL`` env for this call
    (e.g. ``1800`` for 30 min in long workflows; ``0`` to disable).
    """

    request = (
        app_dir
        if isinstance(app_dir, AppLockRequest)
        else AppLockRequest(
            app_dir=app_dir,
            update=update,
            modules=modules,
            check=check,
            quiet=quiet,
            timeout_s=timeout_s,
            resolve_ttl_s=resolve_ttl_s,
        )
    )

    # Apply per-call resolve TTL override via contextvar (concurrency-safe;
    # does not mutate process-global ``os.environ``).
    from . import _resolve_cache

    with _resolve_cache.ttl_override(request.resolve_ttl_s), timeout_budget(request.timeout_s):
        return operations.lock_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            update=request.update,
            modules=request.modules,
            check=request.check,
            quiet=request.quiet,
        )


def sync_app(
    app_dir: PathLike | AppSyncRequest,
    *,
    frozen: bool = False,
    force: bool = False,
    timeout_s: float | None = None,
) -> None:
    """Materialise ``modules/`` so it exactly matches ``nsx.lock``.

    *timeout_s* applies per individual ``git clone`` / ``git fetch``
    invoked during the sync (not to the whole sync run).
    """

    request = (
        app_dir
        if isinstance(app_dir, AppSyncRequest)
        else AppSyncRequest(app_dir=app_dir, frozen=frozen, force=force, timeout_s=timeout_s)
    )
    with timeout_budget(request.timeout_s):
        operations.sync_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            frozen=request.frozen,
            force=request.force,
        )


def outdated_app(
    app_dir: PathLike | AppOutdatedRequest,
    *,
    as_json: bool = False,
    timeout_s: float | None = None,
) -> OutdatedReport:
    """Report git modules whose locked commit lags the upstream constraint.

    Returns an :class:`OutdatedReport` describing every git-hosted
    module inspected (``checked``) and any that could not be resolved
    (``skipped``). The ``as_json`` parameter is accepted for backwards
    compatibility but no longer affects the return value — callers that
    need machine-readable output should use ``report.to_dict()``.
    *timeout_s* applies per ``git ls-remote`` subprocess invoked while
    comparing locked commits to upstream tips.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppOutdatedRequest)
        else AppOutdatedRequest(app_dir=app_dir, as_json=as_json, timeout_s=timeout_s)
    )
    with timeout_budget(request.timeout_s):
        return operations.outdated_app_impl(
            Path(request.app_dir).expanduser().resolve(),
        )


def update_app(
    app_dir: PathLike | AppUpdateRequest,
    *,
    modules: list[str] | None = None,
    timeout_s: float | None = None,
) -> None:
    """Re-resolve module constraints to upstream tip and re-vendor.

    Equivalent to ``nsx lock --update [--module ...] && nsx sync``.
    *timeout_s* applies per individual ``git`` subprocess invoked
    during the re-resolve and re-vendor phases.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppUpdateRequest)
        else AppUpdateRequest(app_dir=app_dir, modules=modules, timeout_s=timeout_s)
    )
    with timeout_budget(request.timeout_s):
        operations.update_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            modules=request.modules,
        )


def cache_info() -> CacheInfo:
    """Return a snapshot of the NSX module artifact cache.

    The result includes the cache root, an "is the cache disabled
    via NSX_DISABLE_MODULE_CACHE" flag, and one
    :class:`~neuralspotx.models.CacheEntry` per content-addressed
    artifact directory. ``CacheInfo.total_size_bytes`` is computed
    by walking each entry — best-effort, errors are silently ignored
    per file. Performs no I/O on stdout.
    """

    return operations.cache_info_impl()


def clean_cache(*, dry_run: bool = False) -> CacheCleanResult:
    """Delete every entry in the NSX module artifact cache.

    With ``dry_run=True`` no entries are removed; the returned
    :class:`~neuralspotx.models.CacheCleanResult.removed_count`
    reflects how many entries *would* be removed by an unconditional
    invocation. Performs no I/O on stdout.
    """

    return operations.clean_cache_impl(dry_run=dry_run)
