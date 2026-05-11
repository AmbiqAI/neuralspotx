"""Lock-file operations: lock, sync, outdated, update."""

from __future__ import annotations

from pathlib import Path

from .. import operations
from .._io import Emitter, using_emitter
from ..models import OutdatedReport
from ..nsx_lock import NsxLock
from ..subprocess_utils import timeout_budget
from ._requests import (
    AppLockRequest,
    AppOutdatedRequest,
    AppSyncRequest,
    AppUpdateRequest,
)

PathLike = str | Path


def lock_app(
    app_dir: PathLike | AppLockRequest,
    *,
    update: bool = False,
    modules: list[str] | None = None,
    check: bool = False,
    quiet: bool = False,
    timeout_s: float | None = None,
    resolve_ttl_s: float | None = None,
    emit: Emitter | None = None,
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
    from .. import _resolve_cache

    with (
        using_emitter(emit),
        _resolve_cache.ttl_override(request.resolve_ttl_s),
        timeout_budget(request.timeout_s),
    ):
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
    emit: Emitter | None = None,
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
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.sync_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            frozen=request.frozen,
            force=request.force,
        )


def outdated_app(
    app_dir: PathLike | AppOutdatedRequest,
    *,
    timeout_s: float | None = None,
) -> OutdatedReport:
    """Report git modules whose locked commit lags the upstream constraint.

    Returns an :class:`OutdatedReport` describing every git-hosted
    module inspected (``checked``) and any that could not be resolved
    (``skipped``). Callers that need machine-readable output should
    use ``report.to_dict()``.
    *timeout_s* applies per ``git ls-remote`` subprocess invoked while
    comparing locked commits to upstream tips.
    """

    request = (
        app_dir
        if isinstance(app_dir, AppOutdatedRequest)
        else AppOutdatedRequest(app_dir=app_dir, timeout_s=timeout_s)
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
    emit: Emitter | None = None,
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
    with using_emitter(emit), timeout_budget(request.timeout_s):
        operations.update_app_impl(
            Path(request.app_dir).expanduser().resolve(),
            modules=request.modules,
        )
