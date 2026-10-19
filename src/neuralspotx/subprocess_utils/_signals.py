"""Turn termination signals into the interrupt path child cleanup already handles.

Children run in their own process group (POSIX) or Job Object (Windows),
so a signal sent to ``nsx`` does not reach them. Ctrl-C arrives as
``KeyboardInterrupt``, and :func:`run`, :func:`run_capture` and
``view_app_impl`` stop their child before re-raising it. ``SIGTERM``
(``timeout``, ``kill``, a canceled CI step) and ``SIGHUP`` (a closed
terminal) end the interpreter without running any of that cleanup, which
leaves the child — a J-Link SWO viewer, ``ninja``, ``JLinkExe`` — running.

:func:`terminate_on_signals` raises :class:`TerminatedBySignal`, a
``KeyboardInterrupt`` subclass, from those signals so the same cleanup
runs. :func:`die_with_parent` is a ``preexec_fn`` that additionally makes
a Linux child exit if ``nsx`` itself is killed outright.
"""

from __future__ import annotations

import ctypes
import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import FrameType

# POSIX signals that should stop ``nsx`` and its children. SIGINT already
# raises KeyboardInterrupt by default.
_TERMINATION_SIGNALS: tuple[str, ...] = ("SIGTERM", "SIGHUP")

# ``prctl(PR_SET_PDEATHSIG, sig)`` from <linux/prctl.h>.
_PR_SET_PDEATHSIG = 1


class TerminatedBySignal(KeyboardInterrupt):
    """Raised in the main thread when ``nsx`` receives a termination signal."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum

    @property
    def signal_name(self) -> str:
        """The signal's name, for example ``SIGTERM``."""

        try:
            return signal.Signals(self.signum).name
        except ValueError:
            return f"signal {self.signum}"

    @property
    def exit_code(self) -> int:
        """Shell convention for a process ended by a signal: 128 + signum."""

        return 128 + self.signum


def _raise_terminated(signum: int, _frame: FrameType | None) -> None:
    raise TerminatedBySignal(signum)


@contextmanager
def terminate_on_signals() -> Iterator[None]:
    """Raise :class:`TerminatedBySignal` on SIGTERM/SIGHUP inside the block.

    A no-op on Windows and outside the main thread (signal handlers can only
    be installed there). Previous handlers are restored on exit.
    """

    if os.name == "nt" or threading.current_thread() is not threading.main_thread():
        yield
        return

    previous: dict[int, Callable[[int, FrameType | None], object] | int | None] = {}
    for name in _TERMINATION_SIGNALS:
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, _raise_terminated)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler if handler is not None else signal.SIG_DFL)


def die_with_parent() -> None:
    """``preexec_fn``: have the Linux kernel send SIGTERM if ``nsx`` dies.

    Covers the case no handler can: ``nsx`` killed with SIGKILL. Best
    effort and Linux-only; elsewhere callers pass ``preexec_fn=None``.
    """

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
    except (OSError, AttributeError):
        pass


def die_with_parent_preexec() -> Callable[[], None] | None:
    """Return :func:`die_with_parent` on Linux, else ``None`` for ``preexec_fn``."""

    return die_with_parent if sys.platform.startswith("linux") else None
