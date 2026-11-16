"""Strict typed reader for the disposable CMake-owned debug context."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..._errors import NSXConfigError

_CMAKE = Path(__file__).resolve().parents[2] / "cmake"


@dataclass(frozen=True, slots=True)
class ConfiguredDebugTarget:
    name: str
    device: str
    speed_khz: int | None
    configured_serial: str | None
    load_address: int | None
    cpu_hz: int | None
    trace_hz: int | None
    elf: Path
    binary: Path
    flash_recipe: Path
    reset_recipe: Path
    flash_unavailable: str | None
    reset_unavailable: str | None
    swo_unavailable: str | None
    rtt_unavailable: str | None

    def unavailable(self, operation: Literal["flash", "reset", "swo", "rtt"]) -> str | None:
        return {
            "flash": self.flash_unavailable,
            "reset": self.reset_unavailable,
            "swo": self.swo_unavailable,
            "rtt": self.rtt_unavailable,
        }[operation]


@dataclass(frozen=True, slots=True)
class ConfiguredDebugContext:
    source: Path
    build: Path
    board: str
    configuration: str
    primary_target: str
    helper_root: Path
    targets: tuple[ConfiguredDebugTarget, ...]

    def target(self, name: str | None = None) -> ConfiguredDebugTarget:
        selected = self.primary_target if name is None else name
        for target in self.targets:
            if target.name == selected:
                return target
        raise NSXConfigError(f"Unknown configured debug target: {selected}")


def _invalid(reason: str) -> NSXConfigError:
    return NSXConfigError(
        f"Invalid debug context: {reason}. Run explicit debug preparation; "
        "upgrade helpers/tool for an unsupported protocol."
    )


def _object(value: object, keys: set[str] | None = None) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise _invalid("expected an object")
    result: dict[str, object] = dict(value)
    if keys is not None and set(result) != keys:
        raise _invalid("unexpected or missing fields")
    return result


def _text(value: object, *, blank: bool = False) -> str:
    if not isinstance(value, str) or (not blank and not value.strip()):
        raise _invalid("expected a nonblank string")
    if any(ord(c) < 32 for c in value):
        raise _invalid("control characters are unsupported")
    return value


def _path(value: object, *, build: Path | None = None) -> Path:
    text = _text(value)
    if any(c in text for c in ';"<>|'):
        raise _invalid("unsupported path characters")
    path = Path(text)
    if not path.is_absolute():
        raise _invalid("path must be absolute")
    if build is not None and (not path.resolve().is_relative_to(build) or path.resolve() == build):
        raise _invalid("output escapes build")
    return path


def _number(value: object, *, optional: bool = False, address: bool = False) -> int | None:
    text = _text(value, blank=optional)
    if optional and not text:
        return None
    pattern = r"(?:0[xX][0-9a-fA-F]+|[0-9]+)" if address else r"[1-9][0-9]*"
    if not re.fullmatch(pattern, text):
        raise _invalid("invalid numeric setting")
    return int(text, 16 if text.lower().startswith("0x") else 10)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _invalid(f"duplicate key {key}")
        result[key] = value
    return result


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise _invalid("expected an array")
    return list(value)


def _parse(data: bytes, source: Path, build: Path, board: str) -> ConfiguredDebugContext:
    try:
        obj = _object(
            json.loads(data, object_pairs_hook=_pairs),
            {
                "schema_version",
                "helper_protocol",
                "input_contract",
                "source",
                "build",
                "board",
                "configuration",
                "primary_target",
                "helper_root",
                "targets",
                "inputs",
                "globs",
            },
        )
    except (ValueError, UnicodeError) as exc:
        raise _invalid("malformed JSON") from exc
    for key in ("schema_version", "helper_protocol", "input_contract"):
        if type(obj[key]) is not int or obj[key] != 1:
            raise _invalid(f"unsupported {key}")
    if _path(obj["source"]) != source or _path(obj["build"]) != build or obj["board"] != board:
        raise _invalid("app/build/board identity mismatch")
    configuration = _text(obj["configuration"], blank=True)
    primary = _text(obj["primary_target"])
    inputs = _array(obj["inputs"])
    if not inputs:
        raise _invalid("missing input fingerprints")
    seen: set[Path] = set()
    for entry in inputs:
        item = _object(entry, {"path", "sha256"})
        path = _path(item["path"])
        if path in seen or not re.fullmatch(r"[0-9a-f]{64}", _text(item["sha256"])):
            raise _invalid("duplicate input or invalid fingerprint")
        seen.add(path)
    for entry in _array(obj["globs"]):
        item = _object(entry)
        if not {"expression", "members"} <= item.keys() or not item.keys() <= {
            "expression",
            "members",
            "recurse",
            "relative",
            "followSymlinks",
            "listDirectories",
        }:
            raise _invalid("unsupported glob record")
        _path(item["expression"])
        for flag in ("recurse", "followSymlinks", "listDirectories"):
            if flag in item and type(item[flag]) is not bool:
                raise _invalid("invalid glob flag")
        if item.get("recurse") or item.get("followSymlinks") or "relative" in item:
            raise _invalid("unsupported glob semantics")
        for member in _array(item["members"]):
            member = _object(member, {"path", "kind"})
            _path(member["path"])
            if member["kind"] not in ("file", "directory"):
                raise _invalid("unsupported glob member")
    targets: list[ConfiguredDebugTarget] = []
    for name, value in _object(obj["targets"]).items():
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name):
            raise _invalid("invalid target name")
        record = _object(
            value,
            {
                "backend",
                "interface",
                "device",
                "speed_khz",
                "configured_serial",
                "load_address",
                "cpu_hz",
                "trace_hz",
                "elf",
                "bin",
                "flash_recipe",
                "reset_recipe",
                "capabilities",
            },
        )
        if record["backend"] != "jlink" or record["interface"] != "SWD":
            raise _invalid("unsupported backend/interface")
        capabilities = _object(record["capabilities"], {"flash", "reset", "swo", "rtt"})
        reasons = {key: _text(value, blank=True) or None for key, value in capabilities.items()}
        reason = reasons["reset"]
        serial = _text(record["configured_serial"], blank=True) or None
        if serial is not None:
            _number(serial)
        targets.append(
            ConfiguredDebugTarget(
                name=name,
                device=_text(record["device"], blank=bool(reason)),
                speed_khz=_number(record["speed_khz"], optional=bool(reason)),
                configured_serial=serial,
                load_address=_number(
                    record["load_address"], optional=bool(reasons["flash"]), address=True
                ),
                cpu_hz=_number(record["cpu_hz"], optional=bool(reasons["swo"])),
                trace_hz=_number(record["trace_hz"], optional=bool(reasons["swo"])),
                elf=_path(record["elf"], build=build),
                binary=_path(record["bin"], build=build),
                flash_recipe=_path(record["flash_recipe"], build=build),
                reset_recipe=_path(record["reset_recipe"], build=build),
                flash_unavailable=reasons["flash"],
                reset_unavailable=reason,
                swo_unavailable=reasons["swo"],
                rtt_unavailable=reasons["rtt"],
            )
        )
    result = ConfiguredDebugContext(
        source,
        build,
        board,
        configuration,
        primary,
        _path(obj["helper_root"]),
        tuple(targets),
    )
    result.target()  # Required registered primary; no first/last-target fallback.
    return result


def _run_script(script: str, *, timeout_s: float, **variables: str) -> None:
    cmake = shutil.which("cmake")
    if not cmake:
        raise _invalid("CMake >=3.31 is required for context validation")
    try:
        result = subprocess.run(
            [
                cmake,
                *(f"-D{key}={value}" for key, value in variables.items()),
                "-P",
                str(_CMAKE / script),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _invalid(f"CMake validation/capture failed: {exc}") from exc
    if result.returncode:
        raise _invalid(result.stderr.strip() or result.stdout.strip() or "CMake validation failed")


def load_debug_context(
    source: Path,
    build: Path,
    board: str,
    *,
    timeout_s: float = 30,
) -> ConfiguredDebugContext:
    """Read and validate without writes, configure, build, or USB access.

    CMake owns glob semantics; its bundled script only reads files. Stable inputs
    are required during this operation, as during preparation/capture.
    """
    source, build = source.resolve(), build.resolve()
    path = build / "nsx-debug/context.json"
    try:
        data = path.read_bytes()
        result = _parse(data, source, build, board)
        _run_script(
            "nsx_debug_validate.cmake",
            timeout_s=timeout_s,
            NSX_DEBUG_BUILD_DIR=str(build),
            NSX_DEBUG_SOURCE_DIR=str(source),
            NSX_DEBUG_BOARD=board,
        )
        if path.read_bytes() != data:
            raise _invalid("context changed during validation")
        return result
    except OSError as exc:
        raise _invalid(f"cannot read prepared context: {exc}") from exc
