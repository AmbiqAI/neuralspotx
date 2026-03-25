"""Helpers for resolving and validating external tool executables."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def tool_path(name: str) -> str | None:
    resolved = shutil.which(name)
    if resolved is not None:
        return resolved

    scripts_dir = Path(sys.executable).parent
    candidates = [scripts_dir / name]
    if sys.platform.startswith("win"):
        candidates.extend(
            [
                scripts_dir / f"{name}.exe",
                scripts_dir / f"{name}.bat",
                scripts_dir / f"{name}.cmd",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def require_tool(name: str) -> None:
    if tool_path(name) is None:
        hint = ""
        if name == "west":
            hint = (
                "\nHint: install `west` or use an NSX install that includes it in the same environment.\n"
                "For `pipx`, reinstall `neuralspotx` so the bundled dependency entry points are available."
            )
        raise SystemExit(f"Required tool not found in PATH: {name}{hint}")


def tool_cmd(name: str, *args: str) -> list[str]:
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
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}")
    if detail:
        print(f"  {detail}")
    if hint and not ok:
        print(f"  Hint: {hint}")
    return ok
