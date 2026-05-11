"""Subprocess runner with timeout-budget + process-tree containment."""

from __future__ import annotations

import os
import select
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from ._verbosity import _VERBOSITY, _effective_timeout
from ._winjob import _ProcessContainer


def run(
    cmd: list[str],
    cwd: Path | None = None,
    *,
    timeout: float | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Run a subprocess, raising on failure or timeout.

    Honours the ambient :func:`timeout_budget` when *timeout* is None.
    On timeout the entire process tree is terminated (POSIX: ``killpg``
    on the new session; Windows: ``TerminateJobObject`` on a
    ``KILL_ON_JOB_CLOSE`` job) and :class:`subprocess.TimeoutExpired`
    is re-raised.

    When *on_line* is supplied, stdout and stderr are merged and the
    callback is invoked once per output line (with the trailing newline
    stripped) as the subprocess produces it. The lines are also
    re-emitted on the parent's stdout so the user-visible output is
    unchanged. When *on_line* is ``None`` the subprocess inherits the
    parent's stdio directly (legacy behaviour).
    """
    effective = _effective_timeout(timeout)
    if on_line is not None:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=(os.name != "nt"),
        )
    else:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            start_new_session=(os.name != "nt"),
        )
    container = _ProcessContainer()
    container.attach(proc)
    try:
        try:
            if on_line is not None and proc.stdout is not None:
                # Stream lines through the callback while still enforcing
                # the wall-clock timeout. We use ``select`` (POSIX) or a
                # blocking readline with a deadline check (Windows) so a
                # subprocess that stops producing newlines cannot escape
                # the budget.
                deadline = None if effective is None else time.monotonic() + effective
                stream = proc.stdout
                use_select = os.name != "nt"
                while True:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            container.terminate(proc)
                            raise subprocess.TimeoutExpired(cmd, effective)
                    else:
                        remaining = None
                    if use_select:
                        ready, _, _ = select.select(
                            [stream],
                            [],
                            [],
                            remaining if remaining is not None else None,
                        )
                        if not ready:
                            # select timed out -> deadline reached
                            container.terminate(proc)
                            raise subprocess.TimeoutExpired(cmd, effective)
                    raw = stream.readline()
                    if not raw:
                        break
                    text_line = raw.rstrip("\n")
                    try:
                        on_line(text_line)
                    except BaseException:
                        # Caller-supplied callback raised; tear down the
                        # subprocess tree before propagating so we don't
                        # leak processes (POSIX) or job-object handles
                        # (Windows).
                        container.terminate(proc)
                        raise
                    sys.stdout.write(raw)
                wait_timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
                rc = proc.wait(timeout=wait_timeout)
            else:
                rc = proc.wait(timeout=effective)
        except subprocess.TimeoutExpired:
            container.terminate(proc)
            raise subprocess.TimeoutExpired(cmd, effective) from None
        except KeyboardInterrupt:
            # ``start_new_session=True`` (POSIX) and the Job Object (Windows)
            # both isolate the child from our terminal's signals, so the
            # Ctrl-C the user typed does NOT propagate.  Kill the whole tree
            # before re-raising, otherwise hung builds/flashes keep running.
            container.terminate(proc)
            raise
    finally:
        container.close()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


def run_capture(
    cmd: list[str],
    cwd: Path | None = None,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture its text output.

    Same timeout / process-tree semantics as :func:`run`.
    """
    effective = _effective_timeout(timeout)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name != "nt"),
    )
    container = _ProcessContainer()
    container.attach(proc)
    try:
        try:
            out, err = proc.communicate(timeout=effective)
        except subprocess.TimeoutExpired:
            container.terminate(proc)
            # Drain any buffered output so the caller can still log it.
            try:
                out, err = proc.communicate(timeout=1)
            except Exception:  # noqa: BLE001
                out, err = "", ""
            raise subprocess.TimeoutExpired(cmd, effective, output=out, stderr=err) from None
        except KeyboardInterrupt:
            # See note in :func:`run` — the child is isolated from our
            # terminal's SIGINT; tear the tree down before re-raising.
            container.terminate(proc)
            raise
    finally:
        container.close()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=out, stderr=err)


def print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    """Echo captured subprocess output to stdout/stderr."""

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")


def jlink_failure_hint(output: str) -> str | None:
    """Translate common SEGGER failures into clearer user-facing hints."""

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
    """Format a subprocess failure for user-facing CLI output."""

    output_parts: list[str] = []
    stdout = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if isinstance(stdout, str) and stdout.strip():
        output_parts.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        output_parts.append(stderr.strip())
    combined_output = "\n".join(output_parts)

    verbose = _VERBOSITY.get()
    hint = jlink_failure_hint(combined_output)
    if hint:
        message = f"{context} failed.\n{hint}"
        if verbose == 0:
            message += "\nRe-run with `--verbose` for the full tool output."
        return message

    message = f"{context} failed with exit code {exc.returncode}."
    if verbose == 0:
        message += "\nRe-run with `--verbose` for the full subprocess traceback."
    return message
