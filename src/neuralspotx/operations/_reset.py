"""Resolve app-local debug settings before invoking explicit reset primitives."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .._errors import NSXConfigError
from ..models import ResetResult
from ._cmake_cache import _cmake_cache_value
from ._common import _resolve_build_context
from ._hardware import reset_target_impl


@dataclass(frozen=True, slots=True)
class _ResetSettings:
    device: str
    speed_khz: int
    probe_serial: str | None


def _app_reset_settings(
    app_dir: Path, *, board: str | None, build_dir: Path | None
) -> _ResetSettings:
    app, _, selected_board, build = _resolve_build_context(
        app_dir, board=board, build_dir=build_dir
    )
    build = build.expanduser().resolve()
    remedy = shlex.join([
        "nsx",
        "configure",
        "--app-dir",
        str(app),
        "--board",
        selected_board,
        "--build-dir",
        str(build),
    ])

    def invalid(reason: str) -> NSXConfigError:
        return NSXConfigError(f"Cannot reset from {build}: {reason}. Run `{remedy}` first.")

    if not (build / "build.ninja").is_file():
        raise invalid("no configured Ninja build")
    source = _cmake_cache_value(build, "CMAKE_HOME_DIRECTORY")
    if source is None or Path(source).resolve() != app:
        raise invalid("CMake cache belongs to a different app or is incomplete")
    if _cmake_cache_value(build, "NSX_BOARD") != selected_board:
        raise invalid("CMake cache does not match the selected board")
    device = _cmake_cache_value(build, "NSX_RESET_DEVICE")
    speed = _cmake_cache_value(build, "NSX_RESET_SPEED_KHZ")
    if (
        not device
        or not device.strip()
        or not speed
        or not speed.isascii()
        or not speed.isdecimal()
    ):
        raise invalid("resolved board reset settings are missing or invalid")
    if int(speed) <= 0:
        raise invalid("resolved board reset speed must be positive")
    return _ResetSettings(
        device=device,
        speed_khz=int(speed),
        probe_serial=_cmake_cache_value(build, "NSX_JLINK_SERIAL") or None,
    )


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
        settings = _app_reset_settings(app_dir, board=board, build_dir=build_dir)
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
