"""Structured event emitter (Phase 4).

The operations layer historically called :func:`print` directly, which
made it impossible for embedders (helia-profiler, agents, GUIs) to
capture progress or pipe machine-readable output. This module defines
the small event/emitter contract that lets every ``api.*`` entry point
accept an optional :class:`Emitter` while preserving today's CLI
output verbatim.

The default emitter writes:

* ``info`` / ``warn`` / ``error`` / ``step`` events to ``sys.stderr``
* ``line`` events to ``sys.stdout``

so that user-facing progress no longer pollutes machine-parseable
``--json`` / ``stdout`` flows but the textual messages users see today
are unchanged.

Operation modules call the module-level helpers (:func:`info`,
:func:`step`, :func:`warn`, :func:`error`, :func:`line`). Each helper
forwards through a :class:`~contextvars.ContextVar` so the active
emitter can be swapped per ``api.*`` call without threading an
``emit=`` argument through every internal helper.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal["info", "warn", "error", "step", "line"]


@dataclass(frozen=True, slots=True)
class Event:
    """One emitted event from the operations layer.

    Attributes:
        kind: Event category.  ``info``/``step`` are progress;
            ``warn``/``error`` flag problems; ``line`` is raw
            machine-readable output (e.g. a diagnostic row).
        message: The fully-formatted text that would have been printed.
        data: Optional structured payload for embedders that want to
            act on the event without re-parsing the message.
    """

    kind: EventKind
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "data": dict(self.data)}


Emitter = Callable[[Event], None]


def default_emitter(event: Event) -> None:
    """Write *event* to stderr (info/warn/error/step) or stdout (line).

    Output is intentionally identical to the legacy ``print(message)``
    behaviour modulo the destination stream.
    """

    stream = sys.stdout if event.kind == "line" else sys.stderr
    print(event.message, file=stream)


_current_emitter: ContextVar[Emitter] = ContextVar("_nsx_current_emitter", default=default_emitter)


@contextlib.contextmanager
def using_emitter(emitter: Emitter | None) -> Iterator[Emitter]:
    """Activate *emitter* for the duration of the ``with`` block.

    ``None`` is treated as "use the default emitter", so callers can
    write ``with using_emitter(emit or default_emitter): ...`` or
    simply ``with using_emitter(emit): ...``.
    """

    active = emitter if emitter is not None else default_emitter
    token = _current_emitter.set(active)
    try:
        yield active
    finally:
        _current_emitter.reset(token)


def emit(event: Event) -> None:
    """Send *event* to the currently active emitter."""

    _current_emitter.get()(event)


def info(message: str, /, **data: Any) -> None:
    emit(Event("info", message, data))


def step(message: str, /, **data: Any) -> None:
    emit(Event("step", message, data))


def warn(message: str, /, **data: Any) -> None:
    emit(Event("warn", message, data))


def error(message: str, /, **data: Any) -> None:
    emit(Event("error", message, data))


def line(message: str, /, **data: Any) -> None:
    emit(Event("line", message, data))


__all__ = [
    "Event",
    "EventKind",
    "Emitter",
    "default_emitter",
    "using_emitter",
    "emit",
    "info",
    "step",
    "warn",
    "error",
    "line",
]
