"""Build / configure / flash / view / clean operations."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .._errors import NSXError
from .._io import info
from ..project_config import _run_cmake_configure
from ..subprocess_utils import (
    extract_view_command,
    format_subprocess_error,
    print_captured_output,
    run,
    run_capture,
)
from . import _common
from ._common import _resolve_build_context
from ._sync import _ensure_app_modules


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
) -> Path:
    """Configure an app with CMake.

    Automatically acquires any missing modules (git clone or packaged
    copy) before running CMake so that a freshly cloned app whose
    ``modules/`` directory is gitignored works out of the box.

    Returns:
        The resolved build directory.
    """

    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    _ensure_app_modules(resolved_app_dir)
    _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain)
    info(f"Configured app at: {resolved_app_dir}")
    info(f"Build directory: {resolved_build_dir}")
    return resolved_build_dir


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    target: str | None = None,
    jobs: int = 8,
    on_line: "Callable[[str], None] | None" = None,
) -> Path:
    """Build an app target and return the build directory."""

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
    resolved_target = target or app_name
    run(
        ["cmake", "--build", str(resolved_build_dir), "--target", resolved_target, "-j", str(jobs)],
        on_line=on_line,
    )
    return resolved_build_dir


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    jobs: int = 8,
    on_line: "Callable[[str], None] | None" = None,
) -> Path:
    """Flash an app using its generated CMake flash target."""

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
    target = f"{app_name}_flash"
    cmd = ["cmake", "--build", str(resolved_build_dir), "--target", target, "-j", str(jobs)]
    if _common.get_verbosity() > 0 or on_line is not None:
        run(cmd, on_line=on_line)
        return resolved_build_dir
    try:
        result = run_capture(cmd)
    except subprocess.CalledProcessError as exc:
        raise NSXError(format_subprocess_error(exc, context="Flash")) from None
    print_captured_output(result)
    return resolved_build_dir


def view_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    reset_on_open: bool = True,
    reset_delay_ms: int = 400,
) -> Path:
    """Launch the SEGGER SWO viewer for an app.

    By default, the viewer is attached first and then the target is reset once.
    This avoids a common race where SWO stays silent until the next reset.
    """

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
    target = f"{app_name}_view"
    view_cmd = extract_view_command(resolved_build_dir, target)
    viewer_proc: subprocess.Popen[bytes] | None = None
    try:
        viewer_proc = subprocess.Popen(view_cmd, cwd=str(resolved_build_dir))
        if reset_on_open:
            if reset_delay_ms > 0:
                time.sleep(reset_delay_ms / 1000.0)
            reset_cmd = [
                "cmake",
                "--build",
                str(resolved_build_dir),
                "--target",
                f"{app_name}_reset",
                "-j",
                "1",
            ]
            if _common.get_verbosity() > 0:
                run(reset_cmd)
            else:
                try:
                    result = run_capture(reset_cmd)
                except subprocess.CalledProcessError as exc:
                    if viewer_proc.poll() is None:
                        viewer_proc.terminate()
                        try:
                            viewer_proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            viewer_proc.kill()
                    raise NSXError(format_subprocess_error(exc, context="Reset")) from None
                print_captured_output(result)
        viewer_proc.wait()
    except subprocess.CalledProcessError as exc:
        raise NSXError(format_subprocess_error(exc, context="View")) from None
    except KeyboardInterrupt:
        # Ctrl-C must take the viewer down with us; otherwise SWO/RTT
        # subprocesses can keep running detached and hold the SEGGER
        # debug interface, blocking subsequent ``nsx flash``/``view``
        # invocations until the user manually kills them.
        if viewer_proc is not None and viewer_proc.poll() is None:
            viewer_proc.terminate()
            try:
                viewer_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                viewer_proc.kill()
                try:
                    viewer_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        raise
    return resolved_build_dir


def clean_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    full: bool = False,
) -> Path:
    """Clean or fully remove an app build directory."""

    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not resolved_build_dir.exists():
        return resolved_build_dir
    if full:
        shutil.rmtree(resolved_build_dir)
        info(f"Removed build directory: {resolved_build_dir}")
        return resolved_build_dir
    if not (resolved_build_dir / "build.ninja").exists():
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
    run(["cmake", "--build", str(resolved_build_dir), "--target", "clean"])
    return resolved_build_dir
