"""Deterministic J-Link flash validation and explicit reset primitives."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from .._errors import NSXConfigError, NSXError, NSXToolchainError
from ..models import ResetResult
from ..subprocess_utils import format_subprocess_error, run_capture
from ..tooling import JLINK_NAMES, find_segger_tool

_FLASH_CONFIRMATION = "flash download: total"
_LOAD_FILE_RE = re.compile(
    r'^\s*LoadFile\s+(?:"(?P<quoted>[^"]+)"|(?P<plain>.+?))\s*,\s*(?P<address>0x[0-9a-fA-F]+|[0-9]+)\s*$',
    re.IGNORECASE | re.MULTILINE,
)
_SWPOI_ADDR = 0x40000004
_SWPOI_VALUE = 0x1B
_SWPOI_DISCONNECT_SIGNATURES = (
    "could not write memory",
    "failed to write memory",
    "memory write failed",
)
_JLINK_FAIL_FAST = "ExitOnError 1\n"


def validate_flash_recipe(build_dir: Path, target: str) -> tuple[Path, Path]:
    """Require a target artifact and a recipe that loads that exact artifact."""

    artifact = build_dir / f"{target}.bin"
    recipe = build_dir / "jlink" / target / "flash_cmds.jlink"
    if not artifact.is_file():
        raise NSXConfigError(
            f"Flash artifact for target '{target}' is missing: {artifact}. "
            f"Build the target with `nsx build --target {target}` and try again."
        )
    if not recipe.is_file():
        raise NSXConfigError(
            f"Generated J-Link flash recipe for target '{target}' is missing: {recipe}. "
            "Re-run `nsx configure` so NSX can generate it."
        )

    text = recipe.read_text(encoding="utf-8")
    match = _LOAD_FILE_RE.search(text)
    if match is None:
        raise NSXConfigError(f"J-Link flash recipe has no valid LoadFile command: {recipe}")
    loaded = Path(match.group("quoted") or match.group("plain").strip())
    if not loaded.is_absolute():
        loaded = recipe.parent / loaded
    if loaded.resolve() != artifact.resolve():
        raise NSXConfigError(
            f"J-Link flash recipe for target '{target}' loads {loaded}, "
            f"but the expected artifact is {artifact}. Re-run `nsx configure`."
        )
    return artifact, recipe


def validate_flash_target_name(target: str) -> None:
    """Reject empty or path-shaped names before joining them under the build tree."""

    if not target or target in {".", ".."} or "/" in target or "\\" in target:
        raise NSXConfigError(
            "Flash target must be a non-empty CMake target name without path separators.",
            field="target",
        )


def flash_programming_verified(output: str) -> bool:
    """Return whether J-Link explicitly confirmed a programming operation."""

    return _FLASH_CONFIRMATION in output.lower()


def _jlink_command(
    *,
    device: str,
    interface: str,
    speed_khz: int,
    probe_serial: str | None,
    command_file: Path,
) -> list[str]:
    executable = find_segger_tool(JLINK_NAMES)
    if executable is None:
        raise NSXToolchainError(
            "JLink executable not found. Install SEGGER J-Link and add it to PATH, "
            "or set JLINK_PATH to the Commander executable."
        )
    cmd = [
        executable,
        "-nogui",
        "1",
        "-device",
        device,
        "-if",
        interface,
        "-speed",
        str(speed_khz),
        "-commandfile",
        str(command_file),
    ]
    if probe_serial:
        cmd[1:1] = ["-USB", probe_serial]
    return cmd


def _run_jlink_script(
    script: str,
    *,
    device: str,
    interface: str,
    speed_khz: int,
    probe_serial: str | None,
) -> subprocess.CompletedProcess[str]:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".jlink", delete=False
        ) as stream:
            # J-Link Commander may print a command error but still return zero
            # unless fail-fast behavior is enabled in the command file. Reset
            # success and reconnect verification must never rely on that
            # otherwise-ambiguous process exit.
            stream.write(_JLINK_FAIL_FAST)
            stream.write(script)
            temporary_path = Path(stream.name)
        cmd = _jlink_command(
            device=device,
            interface=interface,
            speed_khz=speed_khz,
            probe_serial=probe_serial,
            command_file=temporary_path,
        )
        return run_capture(cmd)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _is_expected_swpoi_disconnect(output: str) -> bool:
    """Recognize only a failed SWPOI write to the documented RSTGEN address."""

    lowered = output.lower()
    address_seen = "40000004" in lowered
    value_seen = bool(re.search(r"(?:0x0*1b|\b0*1b\b)", lowered))
    disconnect_seen = any(signature in lowered for signature in _SWPOI_DISCONNECT_SIGNATURES)
    return address_seen and value_seen and disconnect_seen


def _verify_reconnect(
    *, device: str, interface: str, speed_khz: int, probe_serial: str | None
) -> None:
    try:
        _run_jlink_script(
            "connect\nexit\n",
            device=device,
            interface=interface,
            speed_khz=speed_khz,
            probe_serial=probe_serial,
        )
    except subprocess.CalledProcessError as exc:
        raise NSXError(
            format_subprocess_error(exc, context="J-Link reconnect verification")
        ) from None


def reset_target_impl(
    *,
    device: str,
    probe_serial: str | None = None,
    kind: Literal["debug", "swpoi"] = "debug",
    interface: str = "SWD",
    speed_khz: int = 4000,
    verify_reconnect: bool = False,
) -> ResetResult:
    """Perform one explicit J-Link reset and return its classified outcome."""

    if not device.strip():
        raise NSXConfigError("J-Link device must be a non-empty string.", field="device")
    if kind not in ("debug", "swpoi"):
        raise NSXConfigError("Reset kind must be 'debug' or 'swpoi'.", field="kind")
    if speed_khz <= 0:
        raise NSXConfigError("J-Link speed_khz must be greater than zero.", field="speed_khz")

    script = "r\ng\nexit\n"
    if kind == "swpoi":
        script = f"connect\nsleep 1000\nw4 {_SWPOI_ADDR:x} {_SWPOI_VALUE:x}\nsleep 1000\nexit\n"

    expected_disconnect = False
    try:
        _run_jlink_script(
            script,
            device=device,
            interface=interface,
            speed_khz=speed_khz,
            probe_serial=probe_serial,
        )
    except subprocess.CalledProcessError as exc:
        output = "\n".join(
            part for part in (getattr(exc, "stdout", None), getattr(exc, "stderr", None)) if part
        )
        if kind == "swpoi" and _is_expected_swpoi_disconnect(output):
            expected_disconnect = True
        else:
            raise NSXError(format_subprocess_error(exc, context=f"J-Link {kind} reset")) from None

    reconnect_verified: bool | None = None
    if verify_reconnect:
        _verify_reconnect(
            device=device,
            interface=interface,
            speed_khz=speed_khz,
            probe_serial=probe_serial,
        )
        reconnect_verified = True

    return ResetResult(
        device=device,
        kind=kind,
        probe_serial=probe_serial,
        interface=interface,
        speed_khz=speed_khz,
        expected_disconnect=expected_disconnect,
        reconnect_verified=reconnect_verified,
    )


__all__ = [
    "flash_programming_verified",
    "reset_target_impl",
    "validate_flash_recipe",
    "validate_flash_target_name",
]
