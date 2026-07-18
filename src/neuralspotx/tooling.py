"""Helpers for resolving and validating external tool executables."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
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
    """Resolve a SEGGER executable across supported host installations.

    ``JLINK_PATH`` is an explicit override for Commander.  Normal ``PATH``
    lookup remains first-class, followed by the default SEGGER install roots
    used by macOS and Windows.
    """

    if names == JLINK_NAMES:
        override = os.environ.get("JLINK_PATH")
        if override:
            candidate = Path(override).expanduser()
            if candidate.is_file():
                return str(candidate)

    for name in names:
        resolved = tool_path(name)
        if resolved is not None:
            return resolved

    candidates: list[Path] = []
    if names == JLINK_NAMES:
        candidates.extend([
            Path("/usr/local/bin/JLinkExe"),
            Path("/Applications/SEGGER/JLink/JLinkExe"),
        ])
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(env_name)
            if root:
                candidates.append(Path(root) / "SEGGER" / "JLink" / "JLink.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
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
            f"JLink executable not found in PATH (looked for: {', '.join(JLINK_NAMES)})."
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


# Tokens that identify a local SEGGER J-Link process in a command line.
_SEGGER_PROCESS_HINTS = ("jlink", "swoviewer")


def _iter_process_cmdlines() -> Iterator[tuple[int, str]]:
    """Yield ``(pid, cmdline)`` for local processes, best-effort and cheap.

    Prefers reading ``/proc`` directly (no subprocess) on Linux. Falls back
    to a single ``ps`` call on other POSIX systems. Never raises; yields
    nothing when process information cannot be obtained (e.g. Windows).
    """

    proc_root = Path("/proc")
    if proc_root.is_dir():
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if not raw:
                continue
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
            if cmdline:
                yield int(entry.name), cmdline
        return

    try:
        result = subprocess.run(  # noqa: S603,S607 - fixed args, best-effort
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    if result.returncode != 0:
        return
    for raw_line in result.stdout.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        pid_str, _, args = stripped.partition(" ")
        if not pid_str.isdigit():
            continue
        args = args.strip()
        if args:
            yield int(pid_str), args


def find_processes_holding_probe(serial: str) -> list[int]:
    """Return PIDs of local SEGGER processes already bound to *serial*.

    This is a cheap, dependency-free, best-effort check used to warn before
    launching the SWO viewer: a probe held by a stale ``JLinkExe`` /
    ``JLinkSWOViewer`` session is the common cause of SWO attach failures and
    stale output. Matching is high-confidence only — the serial must appear
    verbatim in a SEGGER process command line — so it never produces false
    positives for unrelated processes. The current process is excluded.
    """

    if not serial:
        return []
    needle = serial.lower()
    me = os.getpid()
    hits: list[int] = []
    for pid, cmdline in _iter_process_cmdlines():
        if pid == me:
            continue
        low = cmdline.lower()
        if needle not in low:
            continue
        if not any(hint in low for hint in _SEGGER_PROCESS_HINTS):
            continue
        hits.append(pid)
    return hits
