"""Resolve app-local debug settings before invoking explicit reset primitives."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .._errors import NSXConfigError
from .._probe_selection import ProbeSelection, validate_probe_request
from ..models import ResetResult
from . import _debug_backend as backend
from ._common import _resolve_build_context
from ._debug_context import capture_debug_context
from ._debug_workflow import inspect_build, require_adoption
from ._hardware import reset_target_impl


def reset_impl(
    *,
    device: str | None = None,
    app_dir: Path = Path("."),
    board: str | None = None,
    build_dir: Path | None = None,
    probe_serial: str | None = None,
    discover_probe: bool = False,
    kind: Literal["debug", "swpoi"] = "debug",
    interface: str = "SWD",
    speed_khz: int | None = None,
    verify_reconnect: bool = False,
) -> ResetResult:
    """Reset using an explicit device or the selected app's configured board."""

    probe = backend.ProbeRequest(probe_serial, discover_probe)
    if kind not in ("debug", "swpoi") or not interface.strip():
        raise NSXConfigError("Reset requires kind debug/swpoi and a nonblank interface.")
    if speed_khz is not None and speed_khz <= 0:
        raise NSXConfigError("J-Link speed_khz must be greater than zero.")
    if device is not None:
        if not device.strip():
            raise NSXConfigError("J-Link device must be a non-empty string.")
        serial = ProbeSelection.from_request(probe_serial, discover_probe).resolve()
        return reset_target_impl(
            device=device,
            probe_serial=serial,
            kind=kind,
            interface=interface,
            speed_khz=4000 if speed_khz is None else speed_khz,
            verify_reconnect=verify_reconnect,
        )
    app, name, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    build = build.expanduser().resolve()
    tools = backend.for_board(app, selected)
    reset = backend.require(tools.reset, "Reset", selected, tools)
    return reset(
        backend.DebugBuild(app, selected, build, name),
        probe,
        kind,
        interface,
        speed_khz,
        verify_reconnect,
    )


def _jlink_reset(
    target: backend.DebugBuild,
    probe: backend.ProbeRequest,
    kind: backend.ResetKind,
    interface: str,
    speed_khz: int | None,
    verify_reconnect: bool,
) -> ResetResult:
    app, selected, build = target.app, target.board, target.build
    probe_serial, discover_probe = probe.identity, probe.discover
    validate_probe_request(probe_serial, discover_probe)
    require_adoption(inspect_build(app, build, selected))
    with capture_debug_context(app, build, selected, operation="reset") as snap:
        settings = snap.context.target()
        serial = ProbeSelection.from_request(
            probe_serial, discover_probe, settings.configured_serial
        ).resolve()
        assert settings.speed_khz is not None
        return reset_target_impl(
            device=settings.device,
            probe_serial=serial,
            kind=kind,
            interface=interface,
            speed_khz=settings.speed_khz if speed_khz is None else speed_khz,
            verify_reconnect=verify_reconnect,
        )
