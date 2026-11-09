"""Resolve app-local RTT settings without touching hardware."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

from .._errors import NSXConfigError
from ..models._rtt import RttResult, RttSettings
from ._common import _resolve_build_context
from ._console import warn_console_mismatch
from ._debug_settings import app_debug_settings


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


def _validate_serial(serial: str | None) -> None:
    if serial is not None and (not serial.isascii() or not serial.isdecimal() or int(serial) <= 0):
        raise NSXConfigError("RTT probe serial must be a positive decimal USB serial number.")


def resolve_rtt_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    target: str | None = None,
    probe_serial: str | None = None,
) -> RttSettings:
    """Resolve the exact CMake target artifact and its RTT symbol offline."""
    app, name, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    warn_console_mismatch(app, selected, "rtt", target=target or name)
    build = build.expanduser().resolve()
    debug = app_debug_settings(app, board=selected, build_dir=build)
    target = name if target is None else target
    if not target or target in {".", ".."} or any(c in target for c in "/\\\n\r"):
        raise NSXConfigError("RTT target must be a non-empty CMake target name without separators.")
    serial = debug.probe_serial if probe_serial is None else probe_serial
    _validate_serial(serial)
    manifest = build / "nsx-artifacts" / f"{target}.path"
    try:
        paths = manifest.read_text(encoding="utf-8").splitlines()
        if len(paths) != 1 or not Path(paths[0]).is_absolute():
            raise ValueError("invalid target artifact path")
        elf = Path(paths[0]).resolve()
    except (OSError, ValueError) as exc:
        raise NSXConfigError(
            f"Cannot resolve executable target '{target}' from {manifest}: {exc}. "
            "Run `nsx configure` with this NSX version, then `nsx build`."
        ) from exc
    return RttSettings(
        app, selected, build, target, elf, _rtt_address(elf), debug.device, debug.speed_khz, serial
    )


def rtt_app_impl(
    settings: RttSettings,
    *,
    duration_s: float,
    startup_timeout_s: float,
    capture: Path | None = None,
    on_data: Callable[[bytes], None] | None = None,
) -> RttResult:
    """Capture using the contained native worker; callbacks must return promptly."""
    from .._rtt_capture import capture_rtt

    for name, value in (("duration_s", duration_s), ("startup_timeout_s", startup_timeout_s)):
        if not math.isfinite(value) or value <= 0:
            raise NSXConfigError(f"{name} must be positive and finite.")
    return capture_rtt(
        settings,
        duration_s=duration_s,
        startup_timeout_s=startup_timeout_s,
        capture=capture,
        on_data=on_data,
    )
