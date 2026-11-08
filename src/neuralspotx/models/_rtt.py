"""Resolved RTT capture configuration and outcome."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RttSettings:
    """Offline settings; serial is None until uniquely selected at capture time.

    The ELF must match the firmware already flashed on the target. Resolution
    cannot establish that identity by inspecting the host build alone.
    """

    app_dir: Path
    board: str
    build_dir: Path
    target: str
    elf: Path
    address: int
    device: str
    speed_khz: int
    probe_serial: str | None
    interface: str = "SWD"
    channel: int = 0


@dataclass(frozen=True, slots=True)
class RttResult:
    """A completed capture, including selected USB serial and raw byte count.

    Zero bytes means the channel was ready but silent, not that firmware
    functionality was verified. Capture files retain partial data on failure.
    """

    settings: RttSettings
    bytes_received: int
    capture: Path | None
