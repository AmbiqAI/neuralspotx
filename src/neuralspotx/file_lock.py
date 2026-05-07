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
* Best-effort: if the platform-specific lock primitive is unavailable
  or fails for non-recoverable reasons, the context manager logs a
  warning and proceeds without a lock. NSX should never crash because
  of a missing lock primitive.
* Per-app: callers pass the app directory. The lockfile lives at
  ``<app_dir>/.nsx.sync.lock`` (matched in the example app
  ``.gitignore``). The file is created on demand and left in place
  after release; only its lock state is significant.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

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
    if key in _held_paths:
        # Already locked by an outer scope in this process; just run.
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
        except Exception as exc:  # noqa: BLE001 — best-effort fallback
            _warn_once(f"file lock unavailable ({exc}); proceeding without it.")
        _held_paths.add(key)
        try:
            yield
        finally:
            _held_paths.discard(key)
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


_held_paths: set[str] = set()


class AppLockBusyError(RuntimeError):
    """Raised by :func:`app_lock` in non-blocking mode when busy."""


# ---------------------------------------------------------------------------
# Platform shims
# ---------------------------------------------------------------------------


_warned: set[str] = set()


def _warn_once(msg: str) -> None:
    if msg in _warned:
        return
    _warned.add(msg)
    print(f"warning: {msg}", file=sys.stderr)


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
