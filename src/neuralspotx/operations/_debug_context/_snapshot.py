"""Private operation inputs, unused by the existing debug execution paths."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from ..._errors import NSXConfigError
from ._reader import ConfiguredDebugContext, _parse, _run_script, load_debug_context


@dataclass(frozen=True, slots=True)
class DebugSnapshot:
    context: ConfiguredDebugContext
    target: str
    directory: Path


@contextmanager
def capture_debug_context(
    source: Path,
    build: Path,
    board: str,
    *,
    operation: Literal["flash", "reset", "swo", "rtt"],
    target: str | None = None,
    timeout_s: float = 30,
    swo_reset: bool = True,
) -> Iterator[DebugSnapshot]:
    """Capture stable files; caller retains the context through process cleanup.

    Does not build, configure, select a probe, or execute a hardware command.
    A flash caller must build successfully before capture. RTT callers must
    resolve symbols from the private ELF, not from an earlier offline inspection.
    """
    context = load_debug_context(source, build, board, timeout_s=timeout_s)
    selected = context.target(target)
    selected.require(operation)
    if operation == "swo" and swo_reset:
        selected.require("reset")
    with TemporaryDirectory(prefix="nsx-debug-") as temporary:
        directory = Path(temporary)
        _run_script(
            "nsx_debug_capture.cmake",
            timeout_s=timeout_s,
            NSX_DEBUG_SOURCE_DIR=str(context.source),
            NSX_DEBUG_BUILD_DIR=str(context.build),
            NSX_DEBUG_BOARD=board,
            NSX_DEBUG_TARGET=selected.name,
            NSX_DEBUG_OPERATION=operation,
            NSX_DEBUG_SWO_RESET="ON" if swo_reset else "OFF",
            NSX_DEBUG_CAPTURE_DIR=str(directory),
        )
        captured = _parse(
            (directory / "context.json").read_bytes(),
            context.source,
            context.build,
            board,
        )
        if captured != context:
            raise NSXConfigError("Debug context changed before capture; prepare and retry.")
        yield DebugSnapshot(captured, selected.name, directory)
