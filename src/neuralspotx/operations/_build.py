"""Build / configure / flash / view / clean operations."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from .._errors import NSXConfigError, NSXError
from .._io import info, line, warn
from .._probe_selection import ProbeSelection, validate_probe_request
from ..models import FlashResult
from ..project_config import _run_cmake_configure
from ..subprocess_utils import (
    _ProcessContainer,
    defer_termination,
    die_with_parent_preexec,
    format_subprocess_error,
    print_captured_output,
    run,
    run_capture,
)
from ..subprocess_utils._cmake import run_cmake
from ..tooling import JLINK_SWO_NAMES, find_processes_holding_probe, find_segger_tool
from . import _common
from . import _debug_backend as backend
from ._cmake_cache import _cmake_cache_value
from ._common import _resolve_build_context
from ._configured_toolchain import verify_configured_toolchain
from ._debug_context import capture_debug_context
from ._debug_workflow import inspect_build, prepare_debug, require_adoption, require_physical_debug
from ._hardware import (
    _jlink_command,
    validate_flash_target_name,
)
from ._lock import warn_if_lock_stale
from ._requirements import validate_app_requirements
from ._sync import _ensure_app_modules, regenerate_active_board_glue


def _check_sdk_root(sdk_root: Path | None, *, frozen: bool) -> None:
    """Validate the ``--sdk-root`` escape hatch before any module sync.

    ``sdk_root`` (CMake ``NSX_AMBIQSUITE_ROOT_OVERRIDE``) builds against an
    out-of-tree AmbiqSuite instead of the vendored ``nsx-ambiqsuite`` that
    ``nsx.lock`` records, so the lock, the SBOM and ``--frozen`` no longer
    describe the produced binary. Refuse a path that is not a directory,
    refuse it outright together with ``frozen`` (the two contradict each
    other), and otherwise say loudly that reproducibility is off.
    """

    if sdk_root is None:
        return
    if frozen:
        raise NSXConfigError(
            f"--sdk-root ({sdk_root}) cannot be combined with --frozen: an "
            "out-of-tree AmbiqSuite is not described by nsx.lock, so a frozen "
            "build cannot be verified against it. Drop one of the two flags."
        )
    if not sdk_root.is_dir():
        raise NSXConfigError(
            f"--sdk-root is not a directory: {sdk_root}\n"
            "Pass the root of an out-of-tree AmbiqSuite checkout, or omit the "
            "flag to build against the vendored nsx-ambiqsuite module."
        )
    warn(
        f"Building against out-of-tree AmbiqSuite at {sdk_root} "
        "(NSX_AMBIQSUITE_ROOT_OVERRIDE). nsx.lock, the SBOM and --frozen do "
        "not describe this SDK; the resulting binary is not reproducible from "
        "the app's lock alone."
    )


def _sdk_root_cache_matches(build_dir: Path, sdk_root: Path | None) -> bool:
    """Whether an explicit ``sdk_root`` equals the override cached by CMake.

    ``None`` never forces a reconfigure: a build tree configured with
    ``--sdk-root`` keeps that override until the next explicit configure,
    but says so (see ``_warn_if_cached_sdk_override``).

    ``sdk_root`` is expanded and resolved exactly as
    ``project_config._run_cmake_configure`` does before writing the cache
    entry, so a relative or ``~``-prefixed path an API caller passes still
    compares equal to the cached absolute value instead of reconfiguring
    on every build/flash/view.
    """

    if sdk_root is None:
        _warn_if_cached_sdk_override(build_dir)
        return True
    cached = _cmake_cache_value(build_dir, "NSX_AMBIQSUITE_ROOT_OVERRIDE") or ""
    expanded = str(Path(sdk_root).expanduser().resolve())
    return os.path.normcase(os.path.normpath(cached)) == os.path.normcase(
        os.path.normpath(expanded)
    )


def _warn_if_cached_sdk_override(build_dir: Path) -> None:
    """Say when a build tree still carries a cached ``--sdk-root`` override.

    A plain build/flash/view reuses the existing configure, so an override
    set on an earlier ``nsx configure --sdk-root`` silently stays in force.
    """

    cached = _cmake_cache_value(build_dir, "NSX_AMBIQSUITE_ROOT_OVERRIDE") or ""
    if cached:
        warn(
            f"Build tree {build_dir} was configured with out-of-tree AmbiqSuite "
            f"{cached} (--sdk-root); this build still uses it. Run "
            "`nsx configure` without --sdk-root to return to the vendored SDK."
        )


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    probe_serial: str | None = None,
    sdk_root: Path | None = None,
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
        sdk_root: Out-of-tree AmbiqSuite root (escape hatch; see
            ``_check_sdk_root``). Incompatible with ``frozen``.

    Returns:
        The resolved build directory.
    """

    validate_probe_request(probe_serial)
    _check_sdk_root(sdk_root, frozen=frozen)
    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    inspect_build(
        resolved_app_dir,
        resolved_build_dir,
        resolved_board,
        replace_board=True,
        toolchain=toolchain,
    )
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
    _run_cmake_configure(
        resolved_app_dir,
        resolved_build_dir,
        resolved_board,
        toolchain=toolchain,
        probe_serial=probe_serial,
        sdk_root=sdk_root,
    )
    prepare_debug(resolved_app_dir, resolved_build_dir, resolved_board)
    verify_configured_toolchain(resolved_app_dir, resolved_build_dir, toolchain)
    info(f"Configured app at: {resolved_app_dir}")
    info(f"Build directory: {resolved_build_dir}")
    return resolved_build_dir


def _run_build(
    command: list[str], *, on_line: Callable[[str], None] | None, capture_output: bool
) -> None:
    """Keep normal build streaming; route non-streaming flash output through emitters."""
    if not capture_output:
        run_cmake(command, context="CMake build", on_line=on_line)
        return
    if on_line is not None:
        run(command, on_line=on_line)
        return
    result = run_capture(command)
    if result.stdout:
        line(result.stdout.rstrip())
    if result.stderr:
        info(result.stderr.rstrip())


def _build_target(
    app: Path,
    build: Path,
    target: str,
    jobs: int,
    toolchain: str | None,
    *,
    on_line: Callable[[str], None] | None,
    capture_output: bool,
) -> None:
    command = ["cmake", "--build", str(build), "--target"]
    if toolchain is not None:
        # Regenerate the Ninja manifest alone so a changed CMake input cannot
        # switch compilers and run the requested target in the same invocation.
        _run_build([*command, "build.ninja"], on_line=on_line, capture_output=capture_output)
        verify_configured_toolchain(app, build, toolchain)
    _run_build([*command, target, "-j", str(jobs)], on_line=on_line, capture_output=capture_output)


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    target: str | None = None,
    jobs: int = 8,
    sdk_root: Path | None = None,
    frozen: bool = False,
    _capture_output: bool = False,
    on_line: "Callable[[str], None] | None" = None,
) -> Path:
    """Build an app target and return the build directory.

    Args:
        frozen: Before any configure or Ninja build (which may regenerate),
            verify ``modules/`` against ``nsx.lock`` and raise on any
            drift instead of silently re-vendoring (see
            ``_ensure_app_modules``).
        sdk_root: Out-of-tree AmbiqSuite root (escape hatch; see
            ``_check_sdk_root``). Incompatible with ``frozen``; an explicit
            value that differs from the cached override forces a reconfigure.
    """

    _check_sdk_root(sdk_root, frozen=frozen)
    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    owned = inspect_build(resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain)
    if frozen:
        cached_sdk = _cmake_cache_value(resolved_build_dir, "NSX_AMBIQSUITE_ROOT_OVERRIDE")
        if cached_sdk:
            _check_sdk_root(Path(cached_sdk), frozen=True)
        _ensure_app_modules(resolved_app_dir, resolved_board, frozen=True)
    warn_if_lock_stale(resolved_app_dir, resolved_board)
    regenerate_active_board_glue(resolved_app_dir, resolved_board, build_dir=resolved_build_dir)
    if not (resolved_build_dir / "build.ninja").exists() or not _sdk_root_cache_matches(
        resolved_build_dir, sdk_root
    ):
        _ensure_app_modules(resolved_app_dir, resolved_board, frozen=frozen)
        _run_cmake_configure(
            resolved_app_dir,
            resolved_build_dir,
            resolved_board,
            toolchain=toolchain,
            probe_serial=owned.preference,
            sdk_root=sdk_root,
        )
    validate_app_requirements(resolved_app_dir, resolved_board)
    resolved_target = target or app_name
    _build_target(
        resolved_app_dir,
        resolved_build_dir,
        resolved_target,
        jobs,
        toolchain,
        on_line=on_line,
        capture_output=_capture_output,
    )
    prepare_debug(resolved_app_dir, resolved_build_dir, resolved_board)
    verify_configured_toolchain(resolved_app_dir, resolved_build_dir, toolchain)
    return resolved_build_dir


def preflight_build(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    sdk_root: Path | None = None,
    toolchain: str | None = None,
) -> None:
    """Guard CLI build/update composition with the same read-only ownership check."""
    _check_sdk_root(sdk_root, frozen=False)
    app, _, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    inspect_build(app, build, selected, toolchain=toolchain)


def preflight_flash(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    sdk_root: Path | None = None,
    toolchain: str | None = None,
    target: str | None = None,
    probe: backend.ProbeRequest,
) -> tuple[backend.DebugBuild, backend.FlashDriver]:
    """Validate ownership before flash, including a CLI-requested dependency update."""
    _check_sdk_root(sdk_root, frozen=False)
    app, name, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    tools = backend.for_board(app, selected)
    driver = backend.require(tools.flash, "Flash", selected, tools)
    resolved_target = name if target is None else target
    validate_flash_target_name(resolved_target)
    driver.preflight(probe, inspect_build(app, build, selected, toolchain=toolchain))
    return backend.DebugBuild(app, selected, build, resolved_target), driver


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    target: str | None = None,
    probe_serial: str | None = None,
    discover_probe: bool = False,
    jobs: int = 8,
    sdk_root: Path | None = None,
    frozen: bool = False,
    on_line: Callable[[str], None] | None = None,
) -> FlashResult:
    """Build and capture a target, then connect once without persisting overrides."""
    probe = backend.ProbeRequest(probe_serial, discover_probe)
    _check_sdk_root(sdk_root, frozen=frozen)
    context, driver = preflight_flash(
        app_dir,
        toolchain=toolchain,
        board=board,
        build_dir=build_dir,
        target=target,
        probe=probe,
    )
    try:
        build_app_impl(
            context.app,
            board=context.board,
            build_dir=context.build,
            toolchain=toolchain,
            target=context.target,
            jobs=jobs,
            sdk_root=sdk_root,
            frozen=frozen,
            _capture_output=True,
            on_line=on_line,
        )
        if driver.prepare(context):
            _build_target(
                context.app,
                context.build,
                context.target,
                jobs,
                toolchain,
                on_line=on_line,
                capture_output=True,
            )
    except subprocess.CalledProcessError as exc:
        raise NSXError(
            format_subprocess_error(
                exc, context=f"Flash build for target '{context.target}' in {context.build}"
            )
        ) from None
    verify_configured_toolchain(context.app, context.build, toolchain)
    with driver.capture(context) as prepared:
        return prepared.program(prepared.image, probe, on_line)


def _stop_viewer(
    container: _ProcessContainer, proc: subprocess.Popen[str] | subprocess.Popen[bytes]
) -> None:
    """Stop the viewer's process group; a signal meanwhile is held until it is done.

    Without the deferral, a SIGTERM/SIGHUP/Ctrl-C during the grace wait
    would cut off the escalation to SIGKILL for a viewer that ignores
    SIGTERM.
    """

    with defer_termination():
        container.terminate(proc)


def _probe_serial_from_view_cmd(view_cmd: list[str]) -> str | None:
    """Extract the ``-USB <serial>`` probe serial baked into the view command."""

    for idx, tok in enumerate(view_cmd):
        if tok == "-USB" and idx + 1 < len(view_cmd):
            return view_cmd[idx + 1]
    return None


def _raise_if_viewer_exited(
    proc: subprocess.Popen[str] | subprocess.Popen[bytes],
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


# SoCs confirmed (via J-Link "Secure Part... Secure Chip. Bootloader needs to
# run which will then halt when finish." reset behavior) to hang the SWO
# viewer if it issues a reset after attach: the secure bootloader halts the
# core post-reset and never reaches app code, so the viewer sees no SWO and
# exits during the reset handoff. apollo4l is included on the same secure
# bootloader basis as apollo4p, though not independently hardware-verified.
# Non-secure siblings (apollo3, apollo4, apollo510) are unaffected and keep
# the default viewer-first-reset flow.
_SWO_SECURE_RESET_SOCS = frozenset({"apollo3p", "apollo4l", "apollo4p", "apollo510b"})


def _resolved_view_reset_on_open(soc: str | None, reset_on_open: bool | None) -> bool:
    """Return the effective SWO reset policy for the selected board’s SoC."""

    if reset_on_open is not None:
        return reset_on_open

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
    discover_probe: bool = False,
    sdk_root: Path | None = None,
    frozen: bool = False,
    reset_on_open: bool | None = None,
    reset_delay_ms: int = 400,
    duration_s: float | None = None,
    capture: Path | None = None,
) -> Path:
    """Capture configured SWO inputs and retain one probe through viewer/reset cleanup."""
    probe = backend.ProbeRequest(probe_serial, discover_probe)
    if reset_delay_ms < 0 or (
        duration_s is not None and (not math.isfinite(duration_s) or duration_s <= 0)
    ):
        raise NSXConfigError("SWO delay must be nonnegative and duration positive and finite.")
    _check_sdk_root(sdk_root, frozen=frozen)
    app, name, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    tools = backend.for_board(app, selected)
    view = backend.require(tools.swo, "SWO", selected, tools)
    if reset_on_open is True:
        backend.require(tools.reset, "Reset on SWO open", selected, tools)
    return view(
        backend.DebugBuild(app, selected, build, name),
        probe,
        backend.SwoOptions(
            toolchain, sdk_root, frozen, reset_on_open, reset_delay_ms, duration_s, capture
        ),
    )


def _jlink_view(
    context: backend.DebugBuild, probe: backend.ProbeRequest, options: backend.SwoOptions
) -> Path:
    app, name, selected, build = context.app, context.target, context.board, context.build
    toolchain, sdk_root, frozen = options.toolchain, options.sdk_root, options.frozen
    probe_serial, discover_probe = probe.identity, probe.discover
    validate_probe_request(probe_serial, discover_probe)
    owned = inspect_build(app, build, selected, toolchain=toolchain)
    require_adoption(owned)
    from ._console import warn_console_mismatch

    warn_console_mismatch(app, selected, "swo")
    if frozen:
        cached_sdk = _cmake_cache_value(build, "NSX_AMBIQSUITE_ROOT_OVERRIDE")
        if cached_sdk:
            _check_sdk_root(Path(cached_sdk), frozen=True)
        _ensure_app_modules(app, selected, frozen=True)
    regenerate_active_board_glue(app, selected, build_dir=build)
    if not (build / "build.ninja").exists() or not _sdk_root_cache_matches(build, sdk_root):
        _ensure_app_modules(app, selected, frozen=frozen)
        _run_cmake_configure(
            app,
            build,
            selected,
            toolchain=toolchain,
            probe_serial=owned.preference,
            sdk_root=sdk_root,
        )
    # Sync can restore a missing board overlay. Use the descriptor that is now
    # present for the build before choosing a probe or constructing a reset command.
    descriptor = require_physical_debug(app, selected)
    reset_requested = _resolved_view_reset_on_open(
        descriptor.soc if descriptor else None, options.reset_on_open
    )
    if reset_requested:
        tools = backend.for_board(app, selected)
        backend.require(tools.reset, "Reset on SWO open", selected, tools)
    prepare_debug(app, build, selected, required=True)
    verify_configured_toolchain(app, build, toolchain)
    with capture_debug_context(app, build, selected, operation="swo", target=name) as snap:
        settings = snap.context.target(name)
        if reset_requested and settings.reset_unavailable:
            raise NSXConfigError(f"Reset on SWO open unavailable: {settings.reset_unavailable}")
        serial = ProbeSelection.from_request(
            probe_serial, discover_probe, settings.configured_serial
        ).resolve()
        viewer = find_segger_tool(JLINK_SWO_NAMES)
        if viewer is None:
            raise NSXError("SEGGER SWO viewer not found; install SEGGER and add it to PATH.")
        view_cmd = [
            viewer,
            "-USB",
            serial,
            "-device",
            settings.device,
            "-cpufreq",
            str(settings.cpu_hz),
            "-swofreq",
            str(settings.trace_hz),
            "-itmport",
            "0",
        ]
        assert settings.speed_khz is not None
        reset_cmd = (
            _jlink_command(
                device=settings.device,
                interface="SWD",
                speed_khz=settings.speed_khz,
                probe_serial=serial,
                command_file=snap.directory / "reset_cmds.jlink",
            )
            if reset_requested
            else []
        )
        return _run_viewer(
            build,
            selected,
            name,
            view_cmd,
            reset_cmd,
            reset_on_open=bool(reset_cmd),
            reset_delay_ms=options.reset_delay_ms,
            duration_s=options.duration_s,
            capture=options.capture,
        )


def _run_viewer(
    resolved_build_dir: Path,
    resolved_board: str,
    app_name: str,
    view_cmd: list[str],
    reset_cmd: list[str],
    *,
    reset_on_open: bool,
    reset_delay_ms: int,
    duration_s: float | None,
    capture: Path | None,
) -> Path:
    info(f"Starting SWO viewer for {app_name} on {resolved_board}")

    probe = _probe_serial_from_view_cmd(view_cmd)
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

    start_new_session = os.name != "nt"
    run_cmd = list(view_cmd)
    if stream_output:
        # Line-buffer the viewer so captured output is not block-buffered
        # behind the pipe (the SEGGER CLI buffers heavily otherwise).
        stdbuf = shutil.which("stdbuf")
        if stdbuf is not None:
            run_cmd = [stdbuf, "-oL", "-eL", *run_cmd]

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

    # JLinkSWOViewerCL exits on "any key" — including the EOF it reads
    # immediately when stdin is closed or redirected from /dev/null (any
    # non-interactive invocation: CI, scripts, backgrounded shells).
    # Always give the viewer a pipe we never write to so it can never
    # observe EOF and behaves identically in every context; the viewer
    # is closed with Ctrl-C (handled below) or --duration instead of
    # SEGGER's "press any key" prompt.
    viewer_proc: subprocess.Popen[str] | subprocess.Popen[bytes] | None = None
    # Text-mode handle used only when streaming to a capture file; it is
    # the same process as ``viewer_proc`` but typed for line reads.
    stream_proc: subprocess.Popen[str] | None = None
    # Windows: a kill-on-close Job Object, so the viewer cannot outlive us.
    # Linux: the kernel sends the viewer SIGTERM if ``nsx`` dies outright.
    container = _ProcessContainer()
    preexec_fn = die_with_parent_preexec()
    try:
        # Hold SIGTERM/SIGHUP until viewer_proc is assigned, so the finally
        # below can always reach the viewer.
        with defer_termination():
            if stream_output:
                stream_proc = subprocess.Popen(
                    run_cmd,
                    cwd=str(resolved_build_dir),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=start_new_session,
                    preexec_fn=preexec_fn,
                )
                viewer_proc = stream_proc
            else:
                viewer_proc = subprocess.Popen(
                    run_cmd,
                    cwd=str(resolved_build_dir),
                    stdin=subprocess.PIPE,
                    start_new_session=start_new_session,
                    preexec_fn=preexec_fn,
                )
            container.attach(viewer_proc)
        viewer_pid = getattr(viewer_proc, "pid", "unknown")
        info(f"SWO viewer launched (pid={viewer_pid})")
        if reset_on_open:
            if reset_delay_ms > 0:
                time.sleep(reset_delay_ms / 1000.0)
            _raise_if_viewer_exited(
                viewer_proc,
                phase="startup before reset",
                cmd=run_cmd,
            )
            info(f"Resetting target after viewer attach delay ({reset_delay_ms} ms)")
            if _common.get_verbosity() > 0:
                run(reset_cmd)
            else:
                try:
                    result = run_capture(reset_cmd)
                except subprocess.CalledProcessError as exc:
                    _stop_viewer(container, viewer_proc)
                    raise NSXError(format_subprocess_error(exc, context="Reset")) from None
                print_captured_output(result)
            _raise_if_viewer_exited(
                viewer_proc,
                phase="reset handoff",
                cmd=run_cmd,
            )

        deadline = None if duration_s is None else time.monotonic() + duration_s
        if stream_proc is not None:
            assert capture_file is not None  # noqa: S101 — opened above when streaming
            _stream_viewer(stream_proc, capture_file, deadline)
        # A natural nonzero exit must fail the operation, including unavailable
        # generated viewers. Reaching the requested duration is normal teardown.
        timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
        try:
            returncode = viewer_proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_viewer(container, viewer_proc)
        else:
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, run_cmd)
    except subprocess.CalledProcessError as exc:
        raise NSXError(format_subprocess_error(exc, context="View")) from None
    finally:
        # Every exit — normal, an error, Ctrl-C, or SIGTERM/SIGHUP (raised as
        # TerminatedBySignal by the CLI) — takes the viewer down with us.
        # Otherwise it keeps running detached and holds the SEGGER debug
        # interface, blocking later ``nsx flash``/``view`` on every board.
        try:
            if viewer_proc is not None:
                # A signal during this teardown is raised when it ends; the
                # handles below are still closed.
                _stop_viewer(container, viewer_proc)
        finally:
            container.close()
            if capture_file is not None:
                capture_file.close()
    return resolved_build_dir


def _stream_viewer(
    proc: subprocess.Popen[str],
    sink: TextIO,
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

    lines: "queue.Queue[str | Exception | None]" = queue.Queue()

    def _reader() -> None:
        try:
            for raw in iter(stream.readline, ""):
                lines.put(raw)
        except Exception as exc:
            # Carry reader failures to the owner so its finally tears down the
            # viewer; a decoding/I/O error is not a normal end of the stream.
            lines.put(exc)
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
        if isinstance(item, Exception):
            raise NSXError(f"Cannot read SWO viewer output: {item}") from item
        sys.stdout.write(item)
        sys.stdout.flush()
        sink.write(item)
        sink.flush()
