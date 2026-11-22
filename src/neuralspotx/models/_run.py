"""Evidence from a completed guest program."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunResult:
    """Guest exit code and retained files for one simulator invocation.

    A nonzero guest exit is a completed run. Model or protocol failures raise
    an NSX error instead. Paths are absolute.
    """

    board: str
    elf: Path
    fvp: Path
    guest_exit_code: int
    uart_log: Path
    model_log: Path
