"""Owned build state and explicit preparation, separate from probe execution."""

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .._errors import NSXConfigError
from .._probe_selection import validate_probe_request
from ..subprocess_utils import format_subprocess_error, run_capture
from ._cmake_cache import _cmake_cache_value
from ._debug_context._reader import StaleDebugContextError, _parse, load_debug_context


class DebugState(Enum):
    UNCONFIGURED = "unconfigured"
    LEGACY = "legacy or disabled"
    UNPREPARED = "unprepared"
    VALID = "valid"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class OwnedBuild:
    state: DebugState
    preference: str | None = None


_ADOPT = (
    "NSX app debug requires updated helpers and explicit input-contract adoption. "
    "Set NSX_DEBUG_CONTEXT=ON and NSX_DEBUG_INPUT_CONTRACT=1 before including helpers, "
    "declare nsx_debug_set_primary_target, then run `nsx configure`. "
    "Audit external setting inputs first; frozen mode never upgrades helpers."
)


def inspect_build(app: Path, build: Path, board: str, *, replace_board: bool = False) -> OwnedBuild:
    """Reject invalid state before writes; only declared freshness failures recover."""
    app, build = app.resolve(), build.resolve()
    cache = build / "CMakeCache.txt"
    context = build / "nsx-debug/context.json"
    marker = build / "nsx-debug/protocol"
    if not cache.exists():
        if any(p.exists() for p in (context, marker, build / "build.ninja")):
            raise NSXConfigError("Incomplete existing build; use a fresh build directory.")
        return OwnedBuild(DebugState.UNCONFIGURED)
    try:
        lines = cache.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise NSXConfigError(f"Unreadable CMake cache; use a fresh build directory: {exc}") from exc
    keys: set[str] = set()
    for line in lines:
        if not line or line.startswith(("#", "//")):
            continue
        match = re.fullmatch(r'(?:"([^"]+)"|([^:=]+)):([A-Z_]+)=(.*)', line)
        if match is None:
            raise NSXConfigError("Malformed CMake cache; use a fresh build directory.")
        key = match.group(1) or match.group(2)
        if key in keys:
            raise NSXConfigError(f"Duplicate CMake cache key {key}; use a fresh build directory.")
        keys.add(key)
    source = _cmake_cache_value(build, "CMAKE_HOME_DIRECTORY")
    owner = _cmake_cache_value(build, "CMAKE_CACHEFILE_DIR")
    cached_board = _cmake_cache_value(build, "NSX_BOARD")
    if (
        not source
        or not Path(source).is_absolute()
        or Path(source).resolve() != app
        or not owner
        or not Path(owner).is_absolute()
        or Path(owner).resolve() != build
    ):
        raise NSXConfigError(
            "CMake cache belongs to another app/build or is invalid; use a fresh build directory."
        )
    if not cached_board or (cached_board != board and not replace_board):
        raise NSXConfigError(
            "CMake board mismatch; explicitly run `nsx configure --board ...` to replace it."
        )
    evaluated_board = _cmake_cache_value(build, "NSX_RESET_BOARD")
    if evaluated_board and evaluated_board != cached_board and not replace_board:
        raise NSXConfigError(
            "Incomplete CMake board replacement; explicitly run `nsx configure --board ...` "
            "to set or clear the probe preference before continuing."
        )
    serial = _cmake_cache_value(build, "NSX_JLINK_SERIAL") or None
    validate_probe_request(serial)
    if context.exists():
        try:
            _parse(context.read_bytes(), app, build, cached_board)
        except OSError as exc:
            raise NSXConfigError(f"Cannot read debug context: {exc}") from exc
    if marker.exists():
        try:
            protocol = marker.read_text().strip()
        except (OSError, UnicodeError) as exc:
            raise NSXConfigError(f"Cannot read debug protocol: {exc}") from exc
        if protocol != "1":
            raise NSXConfigError("Unsupported debug helper protocol; upgrade helpers/tool.")
    elif context.exists():
        raise NSXConfigError("Debug context has no helper protocol marker; reconfigure explicitly.")
    enabled = (_cmake_cache_value(build, "NSX_DEBUG_CONTEXT") or "").upper() in {
        "ON",
        "YES",
        "TRUE",
        "1",
    }
    if not enabled or not marker.exists():
        return OwnedBuild(DebugState.LEGACY, serial)
    if not context.exists():
        return OwnedBuild(DebugState.UNPREPARED, serial)
    try:
        load_debug_context(app, build, cached_board)
    except StaleDebugContextError:
        return OwnedBuild(DebugState.STALE, serial)
    return OwnedBuild(DebugState.VALID, serial)


def require_adoption(state: OwnedBuild) -> None:
    if state.state is DebugState.LEGACY:
        raise NSXConfigError(_ADOPT)


def prepare_debug(app: Path, build: Path, board: str, *, required: bool = False) -> bool:
    """Prepare only opted-in builds, through the process-tree-contained runner."""
    state = inspect_build(app, build, board)
    if state.state is DebugState.VALID:
        return False
    if state.state in (DebugState.LEGACY, DebugState.UNCONFIGURED):
        if required:
            raise NSXConfigError(_ADOPT)
        return False
    script = app / "cmake/nsx/nsx_debug_prepare.cmake"
    if not script.is_file():
        raise NSXConfigError(_ADOPT)
    try:
        run_capture(["cmake", f"-DNSX_DEBUG_BUILD_DIR={build.resolve()}", "-P", str(script)])
    except subprocess.CalledProcessError as exc:
        raise NSXConfigError(format_subprocess_error(exc, context="Debug preparation")) from exc
    load_debug_context(app, build, board)
    return True
