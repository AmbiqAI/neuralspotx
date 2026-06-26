"""Typed request dataclasses for the programmatic NSX API."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..constants import DEFAULT_BOARD

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
    board: str = DEFAULT_BOARD
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
    probe_serial: str | None = None
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
        duration_s: When set, terminate the viewer after this many
            seconds so the command always returns (instead of running
            until interrupted).
        capture: When set, line-stream the viewer's output to this file
            in addition to stdout.
    """

    reset_on_open: bool = True
    reset_delay_ms: int = 400
    duration_s: float | None = None
    capture: PathLike | None = None


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
    reset: bool = False
    force: bool = False


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
        timeout_s: Per-subprocess wall-clock budget (seconds). Applied
            to each ``git ls-remote`` invoked while comparing locked
            commits to upstream tips. ``None`` disables the timeout.
    """

    app_dir: PathLike
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
    path: str | None = None
    boards: tuple[str, ...] = ()


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
