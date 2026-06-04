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
    probe_serial: str | None = None,
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
    _run_cmake_configure(
        resolved_app_dir,
        resolved_build_dir,
        resolved_board,
        toolchain=toolchain,
        probe_serial=probe_serial,
    )
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
    probe_serial: str | None = None,
    jobs: int = 8,
    on_line: "Callable[[str], None] | None" = None,
) -> Path:
    """Flash an app using its generated CMake flash target."""

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if probe_serial is not None or not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(
            resolved_app_dir,
            resolved_build_dir,
            resolved_board,
            toolchain=toolchain,
            probe_serial=probe_serial,
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
    probe_serial: str | None = None,
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
    if probe_serial is not None or not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(
            resolved_app_dir,
            resolved_build_dir,
            resolved_board,
            toolchain=toolchain,
            probe_serial=probe_serial,
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
    reset: bool = False,
    force: bool = False,
) -> Path:
    """Clean or fully remove an app build directory.

    With *reset*, also remove the synced ``modules/`` tree and the
    ``.nsx.sync.lock`` file inside *app_dir*, restoring the app to a
    pristine "freshly cloned" state. *board*, *build_dir*, and
    *toolchain* are ignored in reset mode; every ``build/`` and
    ``build_*/`` directory directly under *app_dir* is removed.

    Reset refuses to proceed if it would discard local edits under
    ``modules/`` (any tracked file with mtime newer than
    ``.nsx.sync.lock``). Pass *force* to override.
    """

    if reset:
        return _reset_app(app_dir, force=force)

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


def _reset_app(app_dir: Path, *, force: bool) -> Path:
    """Wipe build dirs + modules/ + .nsx.sync.lock under *app_dir*."""

    resolved_app_dir = app_dir.expanduser().resolve()
    if not (resolved_app_dir / "nsx.yml").exists():
        raise NSXError(
            f"--reset requires an app directory containing nsx.yml; "
            f"none found at {resolved_app_dir}"
        )

    modules_dir = resolved_app_dir / "modules"
    sync_lock = resolved_app_dir / ".nsx.sync.lock"

    if not force and modules_dir.is_dir():
        dirty = _find_locally_modified_modules(modules_dir, sync_lock)
        if dirty:
            preview = "\n  ".join(str(p.relative_to(resolved_app_dir)) for p in dirty[:5])
            more = "" if len(dirty) <= 5 else f"\n  ... and {len(dirty) - 5} more"
            raise NSXError(
                f"Refusing to reset: modules/ contains files modified after the "
                f"last `nsx sync` (these edits would be lost):\n  {preview}{more}\n"
                f"Re-run with --force to discard them."
            )

    build_dirs = sorted(
        p
        for p in resolved_app_dir.iterdir()
        if p.is_dir() and (p.name == "build" or p.name.startswith("build_"))
    )
    for path in build_dirs:
        shutil.rmtree(path)
        info(f"Removed build directory: {path}")

    if modules_dir.is_dir():
        shutil.rmtree(modules_dir)
        info(f"Removed modules directory: {modules_dir}")
    if sync_lock.exists():
        sync_lock.unlink()
        info(f"Removed sync lock: {sync_lock}")

    return resolved_app_dir


def _find_locally_modified_modules(modules_dir: Path, sync_lock: Path) -> list[Path]:
    """Return files under *modules_dir* whose mtime is newer than *sync_lock*.

    Heuristic for "user has hand-edited a synced module since `nsx sync`".
    If *sync_lock* is missing, treat every regular file as suspect so the
    user gets prompted before we wipe a tree we did not place.
    """

    threshold = sync_lock.stat().st_mtime if sync_lock.exists() else None
    suspects: list[Path] = []
    for path in modules_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if threshold is None or path.stat().st_mtime > threshold + 1.0:
            suspects.append(path)
    return suspects
