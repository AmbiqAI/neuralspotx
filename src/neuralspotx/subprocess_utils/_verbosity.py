"""Verbosity + timeout-budget context variables for subprocess helpers."""

from __future__ import annotations

import contextlib
import contextvars
import subprocess
from collections.abc import Callable, Iterator
from typing import TypeVar

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


_T = TypeVar("_T")


class _CallerCallbacks:
    """Recognize a caller's own timeout when it crosses the tool timeout boundary."""

    def __init__(self) -> None:
        self.timeout: subprocess.TimeoutExpired | None = None

    def protect(self, callback: Callable[[_T], None] | None) -> Callable[[_T], None] | None:
        if callback is None:
            return None

        def forward(value: _T) -> None:
            try:
                callback(value)
            except subprocess.TimeoutExpired as exc:
                self.timeout = exc
                raise

        return forward


@contextlib.contextmanager
def timeout_budget(seconds: float | None) -> Iterator[_CallerCallbacks]:
    """Set the per-subprocess timeout and translate tool timeouts to NSXTimeoutError.

    Operations taking caller callbacks can protect them with the yielded scope
    so that a callback's own TimeoutExpired propagates unchanged.
    """
    callbacks = _CallerCallbacks()
    token = _TIMEOUT.set(seconds)
    try:
        yield callbacks
    except subprocess.TimeoutExpired as exc:
        if exc is callbacks.timeout:
            raise
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
