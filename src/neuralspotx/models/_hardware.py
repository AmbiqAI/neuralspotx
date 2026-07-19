"""Structured outcomes for deterministic target hardware operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class FlashResult:
    """Outcome of programming one executable from an NSX app."""

    target: str
    artifact: Path
    recipe: Path
    probe_serial: str | None
    programming_verified: bool


@dataclass(frozen=True, slots=True)
class ResetResult:
    """Outcome of an explicit J-Link reset operation."""

    device: str
    kind: Literal["debug", "swpoi"]
    probe_serial: str | None
    interface: str
    speed_khz: int
    expected_disconnect: bool
    reconnect_verified: bool | None
