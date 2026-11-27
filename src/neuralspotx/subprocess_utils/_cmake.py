"""Run a CMake command with live console output and diagnostics for Python callers."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import IO

from .._errors import NSXToolchainError
from ._cmake_output import _open_shared
from ._runner import _Child, _split_emitted_lines, _start_child, _tail
from ._signals import die_with_parent_preexec
from ._verbosity import _effective_timeout

_TAIL_BYTES = 16 * 1024


def _diagnostic(path: str) -> str:
    with _open_shared(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        stream.seek(max(0, size - _TAIL_BYTES))
        return stream.read(_TAIL_BYTES).decode("utf-8", "replace")


def _deliver_lines(
    proc: subprocess.Popen,
    log: IO[bytes],
    on_line: Callable[[str], None],
    remaining: Callable[[], float | None],
) -> None:
    pending = b""
    while True:
        done = proc.poll() is not None
        end = os.fstat(log.fileno()).st_size
        while log.tell() < end:
            remaining()
            chunk = log.read(min(65536, end - log.tell()))
            segments, pending = _split_emitted_lines(pending + chunk, at_eof=False)
            for text, _ in segments:
                on_line(text)
        if done:
            segments, _ = _split_emitted_lines(pending, at_eof=True)
            for text, _ in segments:
                on_line(text)
            return
        budget = remaining()
        time.sleep(0.02 if budget is None else min(0.02, budget))


def run_cmake(
    cmd: list[str], *, context: str, on_line: Callable[[str], None] | None = None
) -> None:
    """Keep the tool, live output forwarding, and user callbacks under separate ownership."""
    timeout = _effective_timeout(None)
    deadline = None if timeout is None else time.monotonic() + timeout

    def remaining() -> float | None:
        if deadline is None:
            return None
        left = deadline - time.monotonic()
        if left <= 0:
            assert timeout is not None
            raise subprocess.TimeoutExpired(cmd, timeout)
        return left

    def wait(proc: subprocess.Popen) -> int:
        try:
            return proc.wait(timeout=remaining())
        except subprocess.TimeoutExpired as exc:
            raise subprocess.TimeoutExpired(
                cmd, timeout if timeout is not None else exc.timeout
            ) from None

    # Regular files let us drain exactly the output present when CMake exits,
    # even if a detached application helper inherited its output handles.
    with ExitStack() as stack:
        out = stack.enter_context(tempfile.NamedTemporaryFile())
        err = None if on_line is not None else stack.enter_context(tempfile.NamedTemporaryFile())
        paths = [out.name] if err is None else [out.name, err.name]
        # A stalled console pipe must not block the thread enforcing timeout_s.
        relay_child = _Child()
        child = _Child()
        try:
            relay = _start_child(
                relay_child,
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(Path(__file__).with_name("_cmake_output.py")),
                    *paths,
                ],
                stdin=subprocess.PIPE,
                start_new_session=(os.name != "nt"),
                preexec_fn=die_with_parent_preexec(),
            )
            assert relay.stdin is not None
            proc = _start_child(
                child,
                cmd,
                stdout=out,
                stderr=err if err is not None else subprocess.STDOUT,
                start_new_session=(os.name != "nt"),
            )
            if on_line is not None:
                with _open_shared(out.name) as log:
                    _deliver_lines(proc, log, on_line, remaining)
            status = wait(proc)
            relay.stdin.close()
            relay_status = wait(relay)
        except BaseException:
            relay_child.stop()
            child.stop()
            raise
        finally:
            if relay_child.proc is not None and relay_child.proc.stdin is not None:
                relay_child.proc.stdin.close()
            relay_child.release()
            child.release()
        if status:
            output = _diagnostic(out.name)
            errors = _diagnostic(err.name) if err is not None else ""
            cause = subprocess.CalledProcessError(status, cmd, output=output, stderr=errors)
            message = f"{context} failed with exit code {status}: {shlex.join(cmd)}"
            for text in (output, errors):
                if text:
                    message += f"\n{_tail(text)}"
            raise NSXToolchainError(message) from cause
        if relay_status:
            raise NSXToolchainError(f"Could not forward CMake output (exit code {relay_status}).")
