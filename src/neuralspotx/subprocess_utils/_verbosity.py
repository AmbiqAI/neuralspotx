"""Verbosity + timeout-budget context variables for subprocess helpers."""

from __future__ import annotations

import contextlib
import contextvars
import subprocess
from collections.abc import Iterator

from .._errors import NSXTimeoutError

# Verbosity for subprocess error formatting.  Stored in a ContextVar so
# concurrent callers (threads, asyncio tasks, embedders) can scope their
# own level without racing on a module-level global.
_VERBOSITY: contextvars.ContextVar[int] = contextvars.ContextVar(
    "nsx_subprocess_verbosity", default=0
)

# Default wall-clock budget for each subprocess inside a region wrapped
# by :func:`timeout_budget`.  ``None`` means "no implicit timeout";
# explicit ``timeout=`` kwargs on individual calls still apply.
_TIMEOUT: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "nsx_subprocess_timeout", default=None
)


def set_verbosity(level: int) -> None:
    """Set subprocess helper verbosity in the current context."""

    _VERBOSITY.set(level)


def get_verbosity() -> int:
    """Return the verbosity level visible to the current context."""

    return _VERBOSITY.get()


@contextlib.contextmanager
def verbosity(level: int) -> Iterator[None]:
    """Temporarily override subprocess verbosity for a scope."""

    token = _VERBOSITY.set(level)
    try:
        yield
    finally:
        _VERBOSITY.reset(token)


@contextlib.contextmanager
def timeout_budget(seconds: float | None) -> Iterator[None]:
    """Set a default per-subprocess wall-clock timeout for this scope.

    Calls to :func:`run` / :func:`run_capture` inside the ``with`` block
    use *seconds* as their default timeout.  ``None`` clears any
    inherited budget.

    Any :class:`subprocess.TimeoutExpired` raised inside the block is
    translated into :class:`NSXTimeoutError` so callers can rely on the
    typed exception hierarchy.
    """
    token = _TIMEOUT.set(seconds)
    try:
        yield
    except subprocess.TimeoutExpired as exc:
        cmd = exc.cmd
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        raise NSXTimeoutError(
            f"Subprocess timed out after {exc.timeout}s: {cmd_str}",
            command=cmd_str,
            timeout_s=float(exc.timeout) if exc.timeout is not None else None,
        ) from None
    finally:
        _TIMEOUT.reset(token)


def _effective_timeout(explicit: float | None) -> float | None:
    return explicit if explicit is not None else _TIMEOUT.get()
