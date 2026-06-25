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


def _split_emitted_lines(
    pending: bytes, *, at_eof: bool
) -> tuple[list[tuple[str, str]], bytes]:
    """Split streamed *pending* bytes into ``(text, terminator)`` segments.

    Breaks on ``\\n``, ``\\r``, and ``\\r\\n`` (each treated as a single
    line terminator) so carriage-return progress updates (``git``/``ninja``
    redraw a single line with a bare ``\\r``) surface as soon as they
    arrive rather than buffering until the next newline. ``text`` has the
    terminator stripped (for the ``on_line`` callback); ``terminator`` is
    the literal sequence so the caller can re-emit it faithfully and keep
    in-place progress rendering. A trailing bare ``\\r`` at the very end is
    held back (it may be the first half of a ``\\r\\n``) unless *at_eof*.
    Returns the segments plus the still-unconsumed remainder.
    """

    segments: list[tuple[str, str]] = []
    n = len(pending)
    i = 0
    start = 0
    while i < n:
        b = pending[i]
        if b == 0x0A:  # \n
            segments.append((pending[start:i].decode("utf-8", "replace"), "\n"))
            i += 1
            start = i
        elif b == 0x0D:  # \r
            if i + 1 < n:
                if pending[i + 1] == 0x0A:  # \r\n
                    segments.append((pending[start:i].decode("utf-8", "replace"), "\r\n"))
                    i += 2
                else:
                    segments.append((pending[start:i].decode("utf-8", "replace"), "\r"))
                    i += 1
                start = i
            elif at_eof:
                segments.append((pending[start:i].decode("utf-8", "replace"), "\r"))
                i += 1
                start = i
            else:
                # Trailing bare \r that might be the first half of a
                # \r\n straddling the next read; hold it until more bytes.
                break
        else:
            i += 1
    remainder = pending[start:]
    if at_eof and remainder:
        segments.append((remainder.decode("utf-8", "replace"), ""))
        remainder = b""
    return segments, remainder


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
        # Binary pipe: we read raw bytes (``os.read`` on POSIX, ``readline``
        # on Windows) and decode ourselves so we can split on \r as well as
        # \n and re-emit the original terminator for in-place progress.
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
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
                # Stream output through the callback while still enforcing
                # the wall-clock timeout. On POSIX we ``select`` on the raw
                # fd and read chunks so a subprocess that stops producing
                # output (even mid-line) cannot escape the budget, and we
                # split on \r as well as \n so live progress redraws render
                # in place. Windows falls back to a blocking readline with a
                # per-iteration deadline check.
                deadline = None if effective is None else time.monotonic() + effective
                stream = proc.stdout

                def _emit(text_line: str, terminator: str) -> None:
                    try:
                        on_line(text_line)
                    except BaseException:
                        # Caller-supplied callback raised; tear down the
                        # subprocess tree before propagating so we don't
                        # leak processes (POSIX) or job-object handles
                        # (Windows).
                        container.terminate(proc)
                        raise
                    sys.stdout.write(text_line + terminator)
                    if not terminator.endswith("\n"):
                        # A bare \r (or no terminator) won't flush a
                        # line-buffered stdout, so force it for live progress.
                        sys.stdout.flush()

                if os.name != "nt":
                    fd = stream.fileno()
                    pending = b""
                    while True:
                        if deadline is not None:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                container.terminate(proc)
                                raise subprocess.TimeoutExpired(cmd, effective)
                        else:
                            remaining = None
                        ready, _, _ = select.select([fd], [], [], remaining)
                        if not ready:
                            # select timed out -> deadline reached
                            container.terminate(proc)
                            raise subprocess.TimeoutExpired(cmd, effective)
                        chunk = os.read(fd, 65536)
                        at_eof = not chunk
                        pending += chunk
                        segments, pending = _split_emitted_lines(pending, at_eof=at_eof)
                        for text_line, terminator in segments:
                            _emit(text_line, terminator)
                        if at_eof:
                            break
                else:  # pragma: no cover - exercised on Windows CI
                    # Windows pipes don't support ``select``; fall back to a
                    # blocking readline (which only breaks on \n) but still
                    # run each line through the splitter so \r progress within
                    # a completed line is emitted segment-by-segment.
                    pending = b""
                    while True:
                        if deadline is not None:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                container.terminate(proc)
                                raise subprocess.TimeoutExpired(cmd, effective)
                        raw = stream.readline()
                        at_eof = not raw
                        pending += raw
                        segments, pending = _split_emitted_lines(pending, at_eof=at_eof)
                        for text_line, terminator in segments:
                            _emit(text_line, terminator)
                        if at_eof:
                            break
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


# Number of trailing output lines echoed inline on a captured-subprocess
# failure so the user can diagnose without re-running under ``--verbose``.
_ERROR_OUTPUT_TAIL_LINES = 40


def _tail(text: str, *, lines: int = _ERROR_OUTPUT_TAIL_LINES) -> str:
    """Return the last *lines* non-empty-trimmed lines of *text*."""

    rows = text.rstrip().splitlines()
    if len(rows) <= lines:
        return "\n".join(rows)
    return "\n".join(["... (earlier output truncated)", *rows[-lines:]])


def format_subprocess_error(exc: subprocess.CalledProcessError, *, context: str) -> str:
    """Format a subprocess failure for user-facing CLI output.

    When the failing subprocess was *captured* (its stdout/stderr are
    attached to the exception), the trailing lines of that output are
    included inline so the user can diagnose the failure without having
    to re-run the whole command under ``--verbose``.
    """

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
    else:
        message = f"{context} failed with exit code {exc.returncode}."

    # Surface the captured output (or its tail) inline. At verbosity 0 we
    # show the tail; under ``--verbose`` the caller already streamed the
    # full output, so we only append the hint to re-run for the rest.
    if combined_output:
        shown = combined_output if verbose > 0 else _tail(combined_output)
        message += f"\n--- output ---\n{shown}"
        if verbose == 0 and shown != combined_output:
            message += "\n--- (re-run with `--verbose` for the full output) ---"
    elif verbose == 0:
        message += "\nRe-run with `--verbose` for the full tool output."
    return message
