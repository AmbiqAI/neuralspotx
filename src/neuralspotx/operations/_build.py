"""Build / configure / flash / view / clean operations."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from .. import board_descriptors as bd
from .._errors import NSXError
from .._io import info, line, warn
from ..models import FlashResult
from ..project_config import _run_cmake_configure
from ..subprocess_utils import (
    extract_view_command,
    format_subprocess_error,
    print_captured_output,
    run,
    run_capture,
)
from ..tooling import JLINK_NAMES, find_processes_holding_probe, find_segger_tool
from . import _common
from ._common import _resolve_build_context
from ._hardware import (
    flash_programming_verified,
    validate_flash_recipe,
    validate_flash_target_name,
)
from ._lock import warn_if_lock_stale
from ._sync import _ensure_app_modules, regenerate_active_board_glue


def _cmake_cache_value(build_dir: Path, variable: str) -> str | None:
    """Return one typed CMake cache value without invoking CMake."""

    cache_file = build_dir / "CMakeCache.txt"
    try:
        lines = cache_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    prefix = f"{variable}:"
    for cache_line in lines:
        if cache_line.startswith(prefix) and "=" in cache_line:
            return cache_line.split("=", 1)[1]
    return None


def _same_executable_path(cached: str | None, resolved: str | None) -> bool:
    """Compare a CMake FILEPATH cache value with the current discovery result."""

    if resolved is None:
        return cached is None or not cached or cached.endswith("-NOTFOUND")
    if cached is None or not cached or cached.endswith("-NOTFOUND"):
        return False
    return os.path.normcase(os.path.normpath(cached)) == os.path.normcase(
        os.path.normpath(resolved)
    )


def _flash_cache_matches(
    build_dir: Path, *, probe_serial: str | None, jlink_executable: str | None
) -> bool:
    """Return whether cached probe and Commander selection match this flash request."""

    cached_probe = _cmake_cache_value(build_dir, "NSX_JLINK_SERIAL") or ""
    return cached_probe == (probe_serial or "") and _same_executable_path(
        _cmake_cache_value(build_dir, "NSX_JLINK_EXE"), jlink_executable
    )


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    probe_serial: str | None = None,
    frozen: bool = False,
) -> Path:
    """Configure an app with CMake.

    Automatically acquires any missing modules (git clone or packaged
    copy) before running CMake so that a freshly cloned app whose
    ``modules/`` directory is gitignored works out of the box.

    Args:
        frozen: Verify ``modules/`` against ``nsx.lock`` and raise on any
            drift instead of silently re-vendoring (see
            ``_ensure_app_modules``).

    Returns:
        The resolved build directory.
    """

    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
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
    frozen: bool = False,
    on_line: "Callable[[str], None] | None" = None,
) -> Path:
    """Build an app target and return the build directory.

    Args:
        frozen: When a (re)configure is needed (no ``build.ninja`` yet),
            verify ``modules/`` against ``nsx.lock`` and raise on any
            drift instead of silently re-vendoring (see
            ``_ensure_app_modules``).
    """

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    regenerate_active_board_glue(resolved_app_dir, resolved_board)
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
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
    target: str | None = None,
    probe_serial: str | None = None,
    jobs: int = 8,
    frozen: bool = False,
    on_line: "Callable[[str], None] | None" = None,
) -> FlashResult:
    """Flash an app using its generated CMake flash target.

    Args:
        frozen: When a (re)configure is needed (no ``build.ninja`` yet, or
            a ``probe_serial`` was given — see below), verify ``modules/``
            against ``nsx.lock`` and raise on any drift instead of
            silently re-vendoring (see ``_ensure_app_modules``).

            Note: passing ``probe_serial`` always forces a reconfigure
            here (the serial is baked into the CMake cache via
            ``-DNSX_JLINK_SERIAL``, so a stale build must not be flashed
            against a different probe) — ``frozen`` does not skip that
            reconfigure, it only changes how the accompanying module
            sync behaves if one is needed.
    """

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    regenerate_active_board_glue(resolved_app_dir, resolved_board)
    jlink_executable = find_segger_tool(JLINK_NAMES)
    needs_configure = (
        probe_serial is not None
        or not (resolved_build_dir / "build.ninja").exists()
        or not _flash_cache_matches(
            resolved_build_dir,
            probe_serial=probe_serial,
            jlink_executable=jlink_executable,
        )
    )
    if needs_configure:
        _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
        _run_cmake_configure(
            resolved_app_dir,
            resolved_build_dir,
            resolved_board,
            toolchain=toolchain,
            probe_serial=probe_serial,
        )
    resolved_target = target or app_name
    validate_flash_target_name(resolved_target)
    # Build and validate every executable before invoking its CMake flash
    # target. In particular, do not let the primary target's dependency build
    # flow directly into J-Link: a stale or edited recipe must be rejected
    # before it can program an unintended artifact.
    build_cmd = [
        "cmake",
        "--build",
        str(resolved_build_dir),
        "--target",
        resolved_target,
        "-j",
        str(jobs),
    ]
    try:
        build_result = run_capture(build_cmd)
    except subprocess.CalledProcessError as exc:
        raise NSXError(
            format_subprocess_error(exc, context=f"Build for flash target '{resolved_target}'")
        ) from None
    if build_result.stdout:
        line(build_result.stdout.rstrip())
    if build_result.stderr:
        info(build_result.stderr.rstrip())
    artifact, recipe = validate_flash_recipe(resolved_build_dir, resolved_target)

    flash_target = f"{resolved_target}_flash"
    flash_cmd = [
        "cmake",
        "--build",
        str(resolved_build_dir),
        "--target",
        flash_target,
        "-j",
        str(jobs),
    ]
    captured_lines: list[str] = []

    def _capture_line(output_line: str) -> None:
        captured_lines.append(output_line)
        if on_line is not None:
            on_line(output_line)

    if _common.get_verbosity() > 0 or on_line is not None:
        try:
            run(flash_cmd, on_line=_capture_line)
        except subprocess.CalledProcessError as exc:
            raise NSXError(format_subprocess_error(exc, context="Flash")) from None
        output = "\n".join(captured_lines)
    else:
        try:
            result = run_capture(flash_cmd)
        except subprocess.CalledProcessError as exc:
            raise NSXError(format_subprocess_error(exc, context="Flash")) from None
        if result.stdout:
            line(result.stdout.rstrip())
        if result.stderr:
            info(result.stderr.rstrip())
        output = (result.stdout or "") + "\n" + (result.stderr or "")

    if not flash_programming_verified(output):
        raise NSXError(
            f"J-Link flash of target '{resolved_target}' produced no programming confirmation. "
            "The image may not have been programmed; inspect the J-Link output and generated recipe."
        )
    return FlashResult(
        target=resolved_target,
        artifact=artifact,
        recipe=recipe,
        probe_serial=probe_serial,
        programming_verified=True,
    )


def _terminate_viewer(proc: "subprocess.Popen[object]") -> None:
    """Tear down the SWO viewer (and its process group) if still running."""

    if proc.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        return
    try:
        proc.wait(timeout=3)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _probe_serial_from_view_cmd(view_cmd: list[str]) -> str | None:
    """Extract the ``-USB <serial>`` probe serial baked into the view command."""

    for idx, tok in enumerate(view_cmd):
        if tok == "-USB" and idx + 1 < len(view_cmd):
            return view_cmd[idx + 1]
    return None


def _raise_if_viewer_exited(
    proc: "subprocess.Popen[object]",
    *,
    phase: str,
    cmd: list[str],
) -> None:
    """Fail fast when the viewer has already exited during startup/reset sequencing."""

    exit_code = proc.poll()
    if exit_code is None:
        return
    detail = (
        " The probe may already be held by another SEGGER session or the viewer "
        "failed before attach completed."
    )
    raise NSXError(
        f"SWO viewer exited during {phase} with code {exit_code}."
        f"{detail}\n"
        f"Viewer command: {' '.join(cmd)}"
    )


def _view_board_soc(app_dir: Path, board: str) -> str | None:
    """Resolve the SoC for a packaged or app-local board."""

    descriptor = bd.load_board(board)
    if descriptor is not None:
        return descriptor.soc

    board_yaml = app_dir / "boards" / board / "board.yaml"
    if board_yaml.exists():
        return bd.load_board_descriptor_file(board_yaml).soc

    return None


# SoCs confirmed (via J-Link "Secure Part... Secure Chip. Bootloader needs to
# run which will then halt when finish." reset behavior) to hang the SWO
# viewer if it issues a reset after attach: the secure bootloader halts the
# core post-reset and never reaches app code, so the viewer sees no SWO and
# exits during the reset handoff. apollo4l is included on the same secure
# bootloader basis as apollo4p, though not independently hardware-verified.
# Non-secure siblings (apollo3, apollo4, apollo510) are unaffected and keep
# the default viewer-first-reset flow.
_SWO_SECURE_RESET_SOCS = frozenset({"apollo3p", "apollo4l", "apollo4p", "apollo510b"})


def _resolved_view_reset_on_open(
    app_dir: Path, board: str, reset_on_open: bool | None
) -> bool:
    """Return the effective SWO reset policy for *board*."""

    if reset_on_open is not None:
        return reset_on_open

    soc = _view_board_soc(app_dir, board)
    if soc in _SWO_SECURE_RESET_SOCS:
        info(
            "Using attach-only SWO view for this secure-reset SoC; "
            "flash first or pass --reset-on-open to force a reset."
        )
        return False

    return True


def view_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    probe_serial: str | None = None,
    frozen: bool = False,
    reset_on_open: bool | None = None,
    reset_delay_ms: int = 400,
    duration_s: float | None = None,
    capture: Path | None = None,
) -> Path:
    """Launch the SEGGER SWO viewer for an app.

    By default, NSX chooses the board-appropriate reset policy. Most boards
    attach the viewer first and then reset once; Apollo4 secure boards attach
    without resetting because SEGGER's Apollo4 reset path halts in the secure
    boot handoff and can make the SWO viewer exit.

    When *duration_s* is set the viewer is terminated (process group and
    all) after that many seconds, so the command always returns. When
    *capture* is set the viewer's output is line-streamed to both stdout
    and the given file (combined with *duration_s* this gives a bounded,
    automation-friendly SWO capture).

    Args:
        frozen: When a (re)configure is needed (no ``build.ninja`` yet, or
            a ``probe_serial`` was given — same trigger rule as
            ``flash_app_impl``), verify ``modules/`` against ``nsx.lock``
            and raise on any drift instead of silently re-vendoring (see
            ``_ensure_app_modules``).
    """

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    regenerate_active_board_glue(resolved_app_dir, resolved_board)
    if probe_serial is not None or not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
        _run_cmake_configure(
            resolved_app_dir,
            resolved_build_dir,
            resolved_board,
            toolchain=toolchain,
            probe_serial=probe_serial,
        )
    target = f"{app_name}_view"
    view_cmd = extract_view_command(resolved_build_dir, target)
    info(f"Starting SWO viewer for {app_name} on {resolved_board}")
    effective_reset_on_open = _resolved_view_reset_on_open(
        resolved_app_dir, resolved_board, reset_on_open
    )

    probe = probe_serial or _probe_serial_from_view_cmd(view_cmd)
    if probe:
        busy_pids = find_processes_holding_probe(probe)
        if busy_pids:
            pids = ", ".join(str(pid) for pid in busy_pids)
            warn(
                f"Probe {probe} is already in use by another SEGGER session "
                f"(pid(s): {pids}). SWO attach may fail or show stale output; "
                f"close the other session if the viewer stays silent."
            )

    capture_path = Path(capture).expanduser().resolve() if capture is not None else None
    stream_output = capture_path is not None

    popen_kwargs: dict[str, object] = {"cwd": str(resolved_build_dir)}
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    # JLinkSWOViewerCL exits on "any key" — including the EOF it reads
    # immediately when stdin is closed or redirected from /dev/null (any
    # non-interactive invocation: CI, scripts, backgrounded shells).
    # Always give the viewer a pipe we never write to so it can never
    # observe EOF and behaves identically in every context; the viewer
    # is closed with Ctrl-C (handled below) or --duration instead of
    # SEGGER's "press any key" prompt.
    popen_kwargs["stdin"] = subprocess.PIPE
    run_cmd = list(view_cmd)
    if stream_output:
        # Line-buffer the viewer so captured output is not block-buffered
        # behind the pipe (the SEGGER CLI buffers heavily otherwise).
        stdbuf = shutil.which("stdbuf")
        if stdbuf is not None:
            run_cmd = [stdbuf, "-oL", "-eL", *run_cmd]
        popen_kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    # Open (and create the parent dir for) the capture file *before*
    # spawning the viewer. Opening after the viewer is attached would
    # leak the SEGGER process — and keep the J-Link held — if the path
    # is unwritable or its directory does not exist.
    capture_file = None
    if capture_path is not None:
        try:
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            capture_file = open(capture_path, "w", encoding="utf-8")  # noqa: SIM115
        except OSError as exc:
            raise NSXError(f"Cannot open capture file {capture_path}: {exc}") from exc

    viewer_proc: subprocess.Popen[object] | None = None
    try:
        viewer_proc = subprocess.Popen(run_cmd, **popen_kwargs)  # type: ignore[arg-type]
        viewer_pid = getattr(viewer_proc, "pid", "unknown")
        info(f"SWO viewer launched (pid={viewer_pid})")
        if effective_reset_on_open:
            if reset_delay_ms > 0:
                time.sleep(reset_delay_ms / 1000.0)
            _raise_if_viewer_exited(
                viewer_proc,
                phase="startup before reset",
                cmd=run_cmd,
            )
            info(f"Resetting target after viewer attach delay ({reset_delay_ms} ms)")
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
                    _terminate_viewer(viewer_proc)
                    raise NSXError(format_subprocess_error(exc, context="Reset")) from None
                print_captured_output(result)
            _raise_if_viewer_exited(
                viewer_proc,
                phase="reset handoff",
                cmd=run_cmd,
            )

        deadline = None if duration_s is None else time.monotonic() + duration_s
        if stream_output:
            assert capture_file is not None  # noqa: S101 — opened above when streaming
            _stream_viewer(viewer_proc, capture_file, deadline)
            _terminate_viewer(viewer_proc)
        elif deadline is not None:
            try:
                viewer_proc.wait(timeout=duration_s)
            except subprocess.TimeoutExpired:
                _terminate_viewer(viewer_proc)
        else:
            viewer_proc.wait()
    except subprocess.CalledProcessError as exc:
        raise NSXError(format_subprocess_error(exc, context="View")) from None
    except KeyboardInterrupt:
        # Ctrl-C must take the viewer down with us; otherwise SWO/RTT
        # subprocesses can keep running detached and hold the SEGGER
        # debug interface, blocking subsequent ``nsx flash``/``view``
        # invocations until the user manually kills them.
        if viewer_proc is not None:
            _terminate_viewer(viewer_proc)
        raise
    finally:
        if capture_file is not None:
            capture_file.close()
    return resolved_build_dir


def _stream_viewer(
    proc: "subprocess.Popen[object]",
    sink: "object",
    deadline: float | None,
) -> None:
    """Pump viewer stdout to our stdout and *sink* until EOF or *deadline*.

    A daemon reader thread feeds lines through a queue so the wall-clock
    *deadline* is honoured on every platform — including Windows, where
    pipes are not ``select``-able and a bare ``readline()`` would block
    past the requested duration when the viewer is silent.
    """

    import queue
    import threading

    stream = proc.stdout
    if stream is None:
        return

    lines: "queue.Queue[str | None]" = queue.Queue()

    def _reader() -> None:
        try:
            for raw in iter(stream.readline, ""):
                lines.put(raw)
        finally:
            lines.put(None)  # EOF sentinel

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    while True:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
        else:
            remaining = None
        try:
            item = lines.get(timeout=remaining)
        except queue.Empty:
            # deadline reached with no further output
            break
        if item is None:
            # reader hit EOF (viewer exited)
            break
        sys.stdout.write(item)
        sys.stdout.flush()
        sink.write(item)  # type: ignore[attr-defined]
        sink.flush()  # type: ignore[attr-defined]


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
    untracked ``.nsx/`` folder (advisory lock) inside *app_dir*,
    restoring the app to a pristine "freshly cloned" state. *board*,
    *build_dir*, and *toolchain* are ignored in reset mode; every
    ``build/`` and ``build_*/`` directory directly under *app_dir* is
    removed.

    Reset refuses to proceed if it would discard local edits under
    ``modules/`` (any tracked file with mtime newer than
    ``.nsx/sync.lock``). Pass *force* to override.
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
    """Wipe build dirs + modules/ + .nsx/ under *app_dir*."""

    resolved_app_dir = app_dir.expanduser().resolve()
    if not (resolved_app_dir / "nsx.yml").exists():
        raise NSXError(
            f"--reset requires an app directory containing nsx.yml; "
            f"none found at {resolved_app_dir}"
        )

    modules_dir = resolved_app_dir / "modules"
    nsx_dir = resolved_app_dir / ".nsx"
    sync_lock = nsx_dir / "sync.lock"

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
    if nsx_dir.is_dir():
        shutil.rmtree(nsx_dir)
        info(f"Removed .nsx directory: {nsx_dir}")

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
