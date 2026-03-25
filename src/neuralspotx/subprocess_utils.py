"""Helpers for subprocess execution and tool-specific error formatting."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

_VERBOSE = 0


def set_verbosity(level: int) -> None:
    global _VERBOSE
    _VERBOSE = level


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def run_capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )


def print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")


def jlink_failure_hint(output: str) -> str | None:
    lowered = output.lower()
    if "failed to open dll" in lowered:
        return (
            "SEGGER J-Link failed to load its runtime library.\n"
            "Check that the J-Link tools are installed correctly and can run outside `nsx`."
        )
    if "connecting to j-link via usb...failed" in lowered or "cannot connect to j-link" in lowered:
        return (
            "SEGGER J-Link could not connect to the probe over USB.\n"
            "Check the probe connection, power, and that no other tool is holding the J-Link."
        )
    if "cannot connect to target" in lowered or "failed to connect to target" in lowered:
        return (
            "SEGGER J-Link connected, but could not connect to the target device.\n"
            "Check target power, SWD wiring, board selection, and reset state."
        )
    return None


def format_subprocess_error(exc: subprocess.CalledProcessError, *, context: str) -> str:
    output_parts: list[str] = []
    stdout = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if isinstance(stdout, str) and stdout.strip():
        output_parts.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        output_parts.append(stderr.strip())
    combined_output = "\n".join(output_parts)

    hint = jlink_failure_hint(combined_output)
    if hint:
        message = f"{context} failed.\n{hint}"
        if _VERBOSE == 0:
            message += "\nRe-run with `--verbose` for the full tool output."
        return message

    message = f"{context} failed with exit code {exc.returncode}."
    if _VERBOSE == 0:
        message += "\nRe-run with `--verbose` for the full subprocess traceback."
    return message


def extract_view_command(build_dir: Path, target: str) -> list[str]:
    ninja_file = build_dir / "build.ninja"
    if not ninja_file.exists():
        raise SystemExit(f"Missing build.ninja in build directory: {build_dir}")

    lines = ninja_file.read_text(encoding="utf-8").splitlines()
    block_header = f"build CMakeFiles/{target}"
    for idx, line in enumerate(lines):
        if not line.strip().startswith(block_header):
            continue
        for follow in lines[idx + 1 : idx + 8]:
            stripped = follow.strip()
            if stripped.startswith("COMMAND = "):
                command_text = stripped.removeprefix("COMMAND = ")
                if " && " in command_text:
                    _, command_text = command_text.split(" && ", 1)
                return shlex.split(command_text)
        break

    raise SystemExit(
        f"Unable to resolve the SEGGER SWO viewer command for target '{target}' from {ninja_file}"
    )
