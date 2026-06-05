"""Helpers for resolving and validating external tool executables."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ._io import line


def tool_path(name: str) -> str | None:
    """Resolve an executable path from PATH or the active Python scripts dir.

    Args:
        name: Executable base name.

    Returns:
        The resolved executable path, or ``None`` when it cannot be found.
    """

    resolved = shutil.which(name)
    if resolved is not None:
        return resolved

    scripts_dir = Path(sys.executable).parent
    candidates = [scripts_dir / name]
    if sys.platform.startswith("win"):
        candidates.extend([
            scripts_dir / f"{name}.exe",
            scripts_dir / f"{name}.bat",
            scripts_dir / f"{name}.cmd",
        ])

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def require_tool(name: str) -> None:
    """Require that a named tool is available.

    Args:
        name: Executable base name.

    Raises:
        NSXToolchainError: If the tool cannot be resolved.
    """

    from ._errors import NSXToolchainError

    if tool_path(name) is None:
        raise NSXToolchainError(f"Required tool not found in PATH: {name}")


def tool_cmd(name: str, *args: str) -> list[str]:
    """Build a subprocess command with the resolved executable path."""

    tool = tool_path(name)
    if tool is None:
        require_tool(name)
        raise AssertionError("unreachable")
    return [tool, *args]


def doctor_check(
    label: str,
    ok: bool,
    *,
    detail: str | None = None,
    hint: str | None = None,
) -> bool:
    """Print one diagnostic check result in a consistent format."""

    status = "OK" if ok else "FAIL"
    line(f"[{status}] {label}")
    if detail:
        line(f"  {detail}")
    if hint and not ok:
        line(f"  Hint: {hint}")
    return ok


# SEGGER tool names differ across platforms:
#   Linux / macOS: JLinkExe, JLinkSWOViewerCL
#   Windows:       JLink.exe, JLinkSWOViewerCL.exe
# The lists are searched in order — first match wins.
JLINK_NAMES = ["JLinkExe", "JLink"]
JLINK_SWO_NAMES = ["JLinkSWOViewerCL", "JLinkSWOViewer_CL"]


def find_segger_tool(names: list[str]) -> str | None:
    """Resolve the first available SEGGER executable from *names*."""

    for name in names:
        resolved = tool_path(name)
        if resolved is not None:
            return resolved
    return None


@dataclass(frozen=True)
class JLinkProbe:
    """A connected SEGGER J-Link debug probe."""

    index: int
    serial: str
    product: str
    nickname: str | None = None


_EMU_LINE_RE = re.compile(
    r"J-Link\[(?P<index>\d+)\]:.*?"
    r"Serial number:\s*(?P<serial>\S+?)\s*,.*?"
    r"ProductName:\s*(?P<product>[^,]+?)\s*"
    r"(?:,\s*Nickname:\s*(?P<nickname>.+?)\s*)?$"
)


def list_jlink_probes() -> list[JLinkProbe]:
    """Enumerate connected SEGGER J-Link probes via ``JLinkExe ShowEmuList``."""

    exe = find_segger_tool(JLINK_NAMES)
    if exe is None:
        from ._errors import NSXToolchainError

        raise NSXToolchainError(
            "JLink executable not found in PATH (looked for: "
            f"{', '.join(JLINK_NAMES)})."
        )

    try:
        result = subprocess.run(  # noqa: S603 - resolved executable, fixed args
            [exe, "-nogui", "1"],
            input="ShowEmuList\nexit\n",
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    probes: list[JLinkProbe] = []
    for raw in result.stdout.splitlines():
        match = _EMU_LINE_RE.search(raw.strip())
        if match is None:
            continue
        nickname = match.group("nickname")
        if nickname is not None and nickname.strip().lower() in {"<not set>", ""}:
            nickname = None
        probes.append(
            JLinkProbe(
                index=int(match.group("index")),
                serial=match.group("serial"),
                product=match.group("product").strip(),
                nickname=nickname,
            )
        )
    return probes
