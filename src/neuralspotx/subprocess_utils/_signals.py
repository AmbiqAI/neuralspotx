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
runs. :func:`die_with_parent_preexec` returns a ``preexec_fn`` that also
makes a Linux child exit if ``nsx`` itself is killed outright.

POSIX only: on Windows these signals are not delivered this way, so
:func:`terminate_on_signals` is a no-op there and the Job Object is what
ties children to ``nsx``.
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


def _installed_signals() -> list[int]:
    return [s for name in _TERMINATION_SIGNALS if (s := getattr(signal, name, None)) is not None]


@contextmanager
def terminate_on_signals() -> Iterator[None]:
    """Raise :class:`TerminatedBySignal` on SIGTERM/SIGHUP inside the block.

    A signal whose inherited disposition is "ignore" (for example SIGHUP
    under ``nohup``) is left ignored. After the first signal the others
    are ignored too, so cleanup — stopping child processes — runs to the
    end; SIGKILL still works. A no-op on Windows and outside the main
    thread (signal handlers can only be installed there). Previous
    handlers are restored on exit.
    """

    if os.name == "nt" or threading.current_thread() is not threading.main_thread():
        yield
        return

    previous: dict[int, Callable[[int, FrameType | None], object] | int | None] = {}

    def _raise_terminated(signum: int, _frame: FrameType | None) -> None:
        for other in previous:
            signal.signal(other, signal.SIG_IGN)
        raise TerminatedBySignal(signum)

    for signum in _installed_signals():
        current = signal.getsignal(signum)
        if current == signal.SIG_IGN:
            continue
        previous[signum] = current
        signal.signal(signum, _raise_terminated)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            # ``None`` means a handler not installed from Python; the
            # default action is the closest restorable equivalent.
            signal.signal(signum, handler if handler is not None else signal.SIG_DFL)


def die_with_parent_preexec() -> Callable[[], None] | None:
    """Return a ``preexec_fn`` that ties a Linux child's life to ``nsx``.

    The child asks the kernel for SIGTERM when its parent thread exits
    (``PR_SET_PDEATHSIG``), which covers ``nsx`` being killed with SIGKILL,
    where no handler runs. The thread that spawns the child must outlive
    it, which holds for ``view_app_impl``: it waits on the viewer. Returns
    ``None`` off Linux or when ``prctl`` is unavailable.
    """

    if not sys.platform.startswith("linux"):
        return None
    try:
        # Resolve prctl here, in the parent, not after fork in the child.
        prctl = ctypes.CDLL(None, use_errno=True).prctl
    except (OSError, AttributeError):
        return None
    parent_pid = os.getpid()

    def _die_with_parent() -> None:
        prctl(_PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
        # If nsx died between fork and prctl, the signal will never come.
        if os.getppid() != parent_pid:
            os.kill(os.getpid(), signal.SIGTERM)

    return _die_with_parent
