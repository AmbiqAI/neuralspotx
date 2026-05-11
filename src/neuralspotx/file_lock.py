"""Cross-platform per-app advisory file lock for NSX critical sections.

Wraps a region (typically ``nsx lock`` / ``nsx sync`` / ``nsx update``)
with a sentinel lockfile so two concurrent ``nsx`` invocations against
the same app cannot race on ``modules/``, ``nsx.lock``, or the
generated ``cmake/nsx/`` build glue.

Semantics
---------
* Advisory only: an exclusive whole-file lock that another ``nsx``
  process will block on until released. Any other tool that doesn't
  participate (e.g. a developer manually editing files) is unaffected.
* Fail-closed: if the platform-specific lock primitive raises an
  unexpected error, NSX raises :class:`AppLockUnavailableError`
  rather than silently proceeding without synchronisation.
* Per-app: callers pass the app directory. The lockfile lives at
  ``<app_dir>/.nsx.sync.lock`` (matched in the example app
  ``.gitignore``). The file is created on demand and left in place
  after release; only its lock state is significant.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import sys
from collections.abc import Iterator
from pathlib import Path

from ._errors import NSXLockError

LOCK_FILENAME = ".nsx.sync.lock"


def app_lock_path(app_dir: Path) -> Path:
    """Return the per-app lockfile path used by :func:`app_lock`."""

    return app_dir / LOCK_FILENAME


@contextlib.contextmanager
def app_lock(app_dir: Path, *, blocking: bool = True) -> Iterator[None]:
    """Hold an exclusive advisory lock on *app_dir* for the with-block.

    Args:
        blocking: When True (default), wait for the lock if it is held
            by another ``nsx`` process. When False, raise
            :class:`AppLockBusyError` immediately if the lock is busy.

    Reentrant within a single process: nested ``app_lock(same_app_dir)``
    calls become no-ops, so an outer ``nsx update`` (which calls
    ``nsx lock`` then ``nsx sync`` internally) does not self-deadlock.

    On platforms where the advisory-lock primitive is unavailable, the
    context manager runs the body without a lock and prints a one-line
    warning the first time it is invoked.
    """

    key = str(app_dir.resolve())
    held = _held_paths.get()
    if key in held:
        # Already locked by an outer scope in this same thread / async
        # task; just run.  Reentrancy is intentionally per-context, not
        # process-global -- two threads racing on the same app dir must
        # each acquire the OS-level lock.
        yield
        return

    path = app_lock_path(app_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Open / create the lockfile. We hold the fd for the lifetime of the
    # lock; closing the fd implicitly releases the OS-level lock on both
    # POSIX (``flock``) and Windows (``msvcrt.locking``).
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    locked = False
    try:
        try:
            _platform_lock(fd, blocking=blocking)
            locked = True
        except AppLockBusyError:
            raise
        except Exception as exc:  # noqa: BLE001 — primitive failure
            # Fail-closed: the call paths that take this lock
            # (``lock`` / ``sync`` / ``update``) are exactly the ones
            # where racing writers can corrupt ``nsx.lock`` and
            # ``modules/``. Surface a typed error so callers must
            # consciously opt out by not taking the lock.
            raise AppLockUnavailableError(
                f"file lock primitive unavailable for {path}: {exc}."
            ) from exc
        token = _held_paths.set(held | {key})
        try:
            yield
        finally:
            _held_paths.reset(token)
    finally:
        if locked:
            try:
                _platform_unlock(fd)
            except Exception:  # noqa: BLE001
                pass
        try:
            os.close(fd)
        except OSError:
            pass


# Per-context reentrancy tracking.  A ``ContextVar`` holding an
# immutable ``frozenset`` gives each thread / asyncio task its own view,
# so two concurrent callers cannot mistake each other's lock for their
# own and skip the OS-level acquire.
_held_paths: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar(
    "nsx_file_lock_held_paths",
    default=frozenset(),
)


class AppLockBusyError(NSXLockError):
    """Raised by :func:`app_lock` in non-blocking mode when busy."""


class AppLockUnavailableError(NSXLockError):
    """Raised when the lock primitive is unavailable.

    Subclasses :class:`NSXLockError` so the standard CLI / API error
    classification (``cli.main``'s ``NSXError`` handler) routes it the
    same way as other lock-subsystem failures rather than as an
    unclassified ``RuntimeError``.
    """


@contextlib.contextmanager
def file_mutex(path: Path) -> Iterator[None]:
    """Acquire an exclusive blocking lock on *path* for the with-block.

    A lower-level cousin of :func:`app_lock` for serialising
    read-modify-write sequences on shared on-disk artifacts (e.g.
    user-cache JSON files). Differences vs ``app_lock``:

    * Always blocking and always per-call (no reentrancy bookkeeping).
    * Always fail-closed: if the lock primitive raises, that error
      propagates.
    * The caller chooses the lockfile path explicitly. Typically a
      ``<artifact>.lock`` sidecar next to the file being mutated.

    The lockfile is created on demand and left in place after release;
    only its OS-level lock state matters.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        _platform_lock(fd, blocking=True)
        try:
            yield
        finally:
            try:
                _platform_unlock(fd)
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Platform shims
# ---------------------------------------------------------------------------


if sys.platform == "win32":  # pragma: no cover — exercised on Windows CI
    import msvcrt

    def _platform_lock(fd: int, *, blocking: bool) -> None:
        # msvcrt.locking locks a byte range; we lock byte 0. LK_LOCK
        # blocks (with a 10-attempt internal retry); LK_NBLCK returns
        # immediately with an OSError when busy.
        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as exc:
            if not blocking:
                raise AppLockBusyError(str(exc)) from exc
            raise

    def _platform_unlock(fd: int) -> None:
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _platform_lock(fd: int, *, blocking: bool) -> None:
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise AppLockBusyError(str(exc)) from exc

    def _platform_unlock(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
