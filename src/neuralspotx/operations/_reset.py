"""Resolve app-local debug settings before invoking explicit reset primitives."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..models import ResetResult
from ._debug_settings import app_debug_settings
from ._hardware import reset_target_impl


def reset_impl(
    *,
    device: str | None = None,
    app_dir: Path = Path("."),
    board: str | None = None,
    build_dir: Path | None = None,
    probe_serial: str | None = None,
    kind: Literal["debug", "swpoi"] = "debug",
    interface: str = "SWD",
    speed_khz: int | None = None,
    verify_reconnect: bool = False,
) -> ResetResult:
    """Reset using an explicit device or the selected app's configured board."""

    if device is None:
        settings = app_debug_settings(app_dir, board=board, build_dir=build_dir)
        device = settings.device
        if speed_khz is None:
            speed_khz = settings.speed_khz
        if probe_serial is None:
            probe_serial = settings.probe_serial
    return reset_target_impl(
        device=device,
        probe_serial=probe_serial,
        kind=kind,
        interface=interface,
        speed_khz=4000 if speed_khz is None else speed_khz,
        verify_reconnect=verify_reconnect,
    )
