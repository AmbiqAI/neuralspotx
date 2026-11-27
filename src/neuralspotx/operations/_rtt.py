"""Resolve app-local RTT settings without touching hardware."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

from .._errors import NSXConfigError
from .._probe_selection import ProbeSelection, validate_probe_request
from ..models._rtt import RttResult, RttSettings
from . import _debug_backend as backend
from ._common import _resolve_build_context
from ._console import warn_console_mismatch
from ._debug_context import capture_debug_context, load_debug_context
from ._debug_workflow import inspect_build, require_adoption
from ._hardware import validate_flash_target_name


def _rtt_address(elf: Path) -> int:
    try:
        with elf.open("rb") as stream:
            image = ELFFile(stream)
            addresses: set[int] = set()
            for table in image.iter_sections():
                if not isinstance(table, SymbolTableSection):
                    continue
                for symbol in table.get_symbol_by_name("_SEGGER_RTT") or []:
                    index = symbol["st_shndx"]
                    if not isinstance(index, int):
                        continue
                    section = image.get_section(index)
                    address = int(symbol["st_value"])
                    # Only allocated data in a loadable image is meaningful on target.
                    if (
                        address > 0
                        and section["sh_flags"] & 2
                        and section["sh_addr"] <= address < section["sh_addr"] + section["sh_size"]
                        and any(
                            segment["p_type"] == "PT_LOAD"
                            and segment["p_vaddr"]
                            <= address
                            < segment["p_vaddr"] + segment["p_memsz"]
                            for segment in image.iter_segments()
                        )
                    ):
                        addresses.add(address)
            if len(addresses) != 1:
                raise NSXConfigError(
                    f"Expected one defined _SEGGER_RTT address in {elf}; found {len(addresses)}. "
                    "Build an unstripped executable with nsx-segger-rtt enabled."
                )
            return addresses.pop()
    except (OSError, ELFError, ValueError, IndexError) as exc:
        raise NSXConfigError(f"Cannot read RTT ELF {elf}: {exc}. Run `nsx build`.") from exc


def resolve_rtt_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    target: str | None = None,
    probe_serial: str | None = None,
    discover_probe: bool = False,
) -> RttSettings:
    """Resolve the exact CMake target artifact and its RTT symbol offline."""
    probe = backend.ProbeRequest(probe_serial, discover_probe)
    app, name, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    target = name if target is None else target
    validate_flash_target_name(target)
    tools = backend.for_board(app, selected)
    rtt = backend.require(tools.rtt, "RTT", selected, tools)
    warn_console_mismatch(app, selected, "rtt", target=target)
    return rtt.resolve(
        backend.DebugBuild(app, selected, build, target),
        probe,
    )


def _resolve_jlink_rtt(context: backend.DebugBuild, probe: backend.ProbeRequest) -> RttSettings:
    app, selected, build, target = context.app, context.board, context.build, context.target
    probe_serial, discover_probe = probe.identity, probe.discover
    validate_probe_request(probe_serial, discover_probe)
    require_adoption(inspect_build(app, build, selected))
    debug = load_debug_context(app, build, selected).target(target)
    if debug.rtt_unavailable:
        raise NSXConfigError(f"RTT unavailable: {debug.rtt_unavailable}")
    serial = ProbeSelection.from_request(
        probe_serial, discover_probe, debug.configured_serial
    ).serial
    assert debug.speed_khz is not None
    return RttSettings(
        app,
        selected,
        build,
        target,
        debug.elf,
        _rtt_address(debug.elf),
        debug.device,
        debug.speed_khz,
        serial,
    )


def rtt_app_impl(
    settings: RttSettings,
    *,
    probe_serial: str | None = None,
    discover_probe: bool = False,
    duration_s: float,
    startup_timeout_s: float,
    capture: Path | None = None,
    on_data: Callable[[bytes], None] | None = None,
) -> RttResult:
    """Capture using the contained native worker; callbacks must return promptly."""
    for name, value in (("duration_s", duration_s), ("startup_timeout_s", startup_timeout_s)):
        if not math.isfinite(value) or value <= 0:
            raise NSXConfigError(f"{name} must be positive and finite.")
    tools = backend.for_board(settings.app_dir, settings.board)
    rtt = backend.require(tools.rtt, "RTT", settings.board, tools)
    return rtt.capture(
        settings,
        backend.ProbeRequest(probe_serial, discover_probe),
        duration_s,
        startup_timeout_s,
        capture,
        on_data,
    )


def _capture_jlink_rtt(
    settings: RttSettings,
    probe: backend.ProbeRequest,
    duration_s: float,
    startup_timeout_s: float,
    capture: Path | None,
    on_data: Callable[[bytes], None] | None,
) -> RttResult:
    from .._rtt_capture import capture_rtt

    probe_serial, discover_probe = probe.identity, probe.discover
    validate_probe_request(probe_serial, discover_probe)
    require_adoption(inspect_build(settings.app_dir, settings.build_dir, settings.board))
    with capture_debug_context(
        settings.app_dir,
        settings.build_dir,
        settings.board,
        operation="rtt",
        target=settings.target,
    ) as snap:
        target = snap.context.target(settings.target)
        assert target.speed_khz is not None
        current = replace(
            settings,
            elf=target.elf,
            address=_rtt_address(snap.directory / "firmware.elf"),
            device=target.device,
            speed_khz=target.speed_khz,
            probe_serial=ProbeSelection.from_request(
                probe_serial, discover_probe, target.configured_serial
            ).serial,
        )
        return capture_rtt(
            current,
            duration_s=duration_s,
            startup_timeout_s=startup_timeout_s,
            capture=capture,
            on_data=on_data,
        )
