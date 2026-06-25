"""Doctor diagnostics — verifies host toolchain prerequisites."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .._io import line
from ..models import DoctorCheck, DoctorReport
from ..subprocess_utils import jlink_failure_hint
from ..tooling import (
    JLINK_NAMES,
    JLINK_SWO_NAMES,
    doctor_check,
    find_segger_tool,
    tool_path,
)


class _Reporter:
    """Collect :class:`DoctorCheck` rows while preserving the historic
    side-effect of printing each check immediately."""

    def __init__(self) -> None:
        self.checks: list[DoctorCheck] = []
        self.notes: list[str] = []

    def check(
        self,
        label: str,
        ok: bool,
        *,
        required: bool = True,
        detail: str | None = None,
        hint: str | None = None,
    ) -> bool:
        # ``doctor_check`` performs the user-visible print so the CLI
        # output remains byte-identical; we record the structured row
        # alongside it for embedders.
        doctor_check(label, ok, detail=detail, hint=hint)
        self.checks.append(
            DoctorCheck(label=label, ok=ok, required=required, detail=detail, hint=hint)
        )
        return ok

    def note(self, line_text: str) -> None:
        line(line_text)
        self.notes.append(line_text.strip())


def _find_in_dir(directory: Path, name: str) -> str | None:
    """Look for *name* in *directory*, trying ``.exe`` on Windows."""
    candidate = directory / name
    if candidate.is_file():
        return str(candidate)
    if sys.platform.startswith("win"):
        exe = directory / f"{name}.exe"
        if exe.is_file():
            return str(exe)
    return None


def doctor_impl() -> DoctorReport:
    """Run the NSX environment diagnostics.

    Returns the structured :class:`DoctorReport`. The CLI is responsible
    for raising :class:`~neuralspotx._errors.NSXToolchainError` when
    ``report.ok`` is false; ``api.doctor()`` itself never raises so
    embedders can render or act on partial failures.
    """

    r = _Reporter()

    python_exe = shutil.which("python") or shutil.which("python3")
    r.check("Python", python_exe is not None, detail=python_exe)
    r.check("uv", tool_path("uv") is not None, detail=tool_path("uv"))
    r.check("cmake", tool_path("cmake") is not None, detail=tool_path("cmake"))
    r.check("ninja", tool_path("ninja") is not None, detail=tool_path("ninja"))
    r.check(
        "git",
        tool_path("git") is not None,
        detail=tool_path("git"),
        hint="Install git.",
    )

    # Informational: surface the active git protocol allow-list so
    # users (and supply-chain audits) can see at a glance which
    # transports nsx will refuse before invoking ``git``.
    from ..subprocess_utils import GIT_PROTOCOL_ALLOWLIST_FLAGS

    r.note("  git protocol allow-list: " + " ".join(GIT_PROTOCOL_ALLOWLIST_FLAGS))

    # Package self-check: the board registry (board.yaml descriptors and the
    # canonical _BOARD_ORDER they derive) is validated here rather than at
    # import time, so a malformed/drifted descriptor is reported instead of
    # making the whole package unimportable.
    from ..constants import validate_board_registry

    board_problems = validate_board_registry()
    r.check(
        "Board registry",
        not board_problems,
        detail=(
            "; ".join(board_problems)
            if board_problems
            else "packaged board descriptors are consistent"
        ),
        hint=(
            "Packaged board.yaml descriptors are inconsistent — this is a "
            "neuralspotx packaging bug; please report it."
            if board_problems
            else None
        ),
    )
    r.check(
        "arm-none-eabi-gcc",
        tool_path("arm-none-eabi-gcc") is not None,
        detail=tool_path("arm-none-eabi-gcc"),
        hint="Install the Arm GNU toolchain and ensure it is in PATH.",
    )

    # armclang is optional — report but do not fail doctor when missing.
    armclang_path = tool_path("armclang")
    armlink_path = tool_path("armlink")
    fromelf_path = tool_path("fromelf")
    if armclang_path or armlink_path or fromelf_path:
        r.check(
            "armclang",
            armclang_path is not None,
            required=False,
            detail=armclang_path,
            hint="Install Arm Compiler for Embedded (armclang) if you want the armclang toolchain.",
        )
        r.check(
            "armlink",
            armlink_path is not None,
            required=False,
            detail=armlink_path,
            hint="armlink should ship alongside armclang.",
        )
        r.check(
            "fromelf",
            fromelf_path is not None,
            required=False,
            detail=fromelf_path,
            hint="fromelf should ship alongside armclang.",
        )
    else:
        r.note("  (armclang toolchain not detected — optional)")

    # ATfE (Arm Toolchain for Embedded) — optional.
    # ATFE_ROOT env var points to the install dir; tools are NOT on PATH.
    atfe_root = os.environ.get("ATFE_ROOT", "")
    if atfe_root:
        atfe_bin = Path(atfe_root) / "bin"
        atfe_clang = _find_in_dir(atfe_bin, "clang")
        atfe_objcopy = _find_in_dir(atfe_bin, "llvm-objcopy")
        atfe_newlib_cfg = _find_in_dir(atfe_bin, "newlib.cfg")
        r.check(
            "ATfE clang",
            atfe_clang is not None,
            required=False,
            detail=atfe_clang,
            hint="ATFE_ROOT is set but clang not found in $ATFE_ROOT/bin.",
        )
        r.check(
            "ATfE llvm-objcopy",
            atfe_objcopy is not None,
            required=False,
            detail=atfe_objcopy,
            hint="llvm-objcopy should ship alongside ATfE clang.",
        )
        r.check(
            "ATfE newlib.cfg",
            atfe_newlib_cfg is not None,
            required=False,
            detail=atfe_newlib_cfg,
            hint="Install the ATfE newlib overlay — extract ATfE-newlib-overlay on top of the ATfE install.",
        )
    else:
        r.note("  (ATfE toolchain not detected — set ATFE_ROOT to enable; optional)")

    jlink_path = find_segger_tool(JLINK_NAMES)
    jlink_ok = jlink_path is not None
    r.check(
        "SEGGER J-Link",
        jlink_ok,
        detail=jlink_path,
        hint="Install the SEGGER J-Link package and ensure JLinkExe (Linux/macOS) or JLink (Windows) is in PATH.",
    )

    swo_path = find_segger_tool(JLINK_SWO_NAMES)
    r.check(
        "SEGGER JLinkSWOViewerCL",
        swo_path is not None,
        detail=swo_path,
        hint="Install the SEGGER J-Link package and ensure JLinkSWOViewerCL is in PATH.",
    )

    if jlink_ok:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jlink", encoding="utf-8") as f:
            f.write("q")
            cmd_file_path = f.name
        try:
            probe = subprocess.run(
                [jlink_path, "-CommandFile", cmd_file_path, "-NoGui", "1"],
                check=True,
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=10,
            )
            output = (probe.stdout or "") + (probe.stderr or "")
            dll_hint = jlink_failure_hint(output)
            if dll_hint:
                r.check(
                    "SEGGER J-Link runtime",
                    False,
                    detail=dll_hint.splitlines()[0],
                    hint="Run `JLinkExe` directly and reinstall SEGGER tools if the runtime is broken.",
                )
            else:
                r.check(
                    "SEGGER J-Link runtime",
                    True,
                    detail="JLinkExe launched successfully.",
                )
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            dll_hint = jlink_failure_hint(output)
            if dll_hint:
                r.check(
                    "SEGGER J-Link runtime",
                    False,
                    detail=dll_hint.splitlines()[0],
                    hint="Run `JLinkExe` directly and reinstall SEGGER tools if the runtime is broken.",
                )
            else:
                # JLinkExe exited non-zero but produced no recognised
                # runtime-failure hint. Treat as a warning rather than a
                # success — a non-zero exit on a no-arg probe almost
                # always means the tool is misbehaving in this
                # environment, even if we can't classify the failure.
                first_line = output.strip().splitlines()[0] if output.strip() else ""
                detail = f"JLinkExe exited with code {exc.returncode}" + (
                    f": {first_line}" if first_line else ""
                )
                r.check(
                    "SEGGER J-Link runtime",
                    False,
                    detail=detail,
                    hint=(
                        "Run `JLinkExe` directly to inspect the failure; "
                        "reinstall SEGGER tools if the runtime is broken."
                    ),
                )
        except subprocess.TimeoutExpired:
            r.check(
                "SEGGER J-Link runtime",
                False,
                detail="JLinkExe timed out (>10s).",
                hint="JLinkExe may be hanging. Run it directly to diagnose.",
            )
        finally:
            if os.path.exists(cmd_file_path):
                os.remove(cmd_file_path)

    return DoctorReport(checks=tuple(r.checks), notes=tuple(r.notes))
