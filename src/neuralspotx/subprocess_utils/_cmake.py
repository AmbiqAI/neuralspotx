"""Run a CMake command with live console output and diagnostics for Python callers."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import IO

from .._errors import NSXToolchainError
from ._cmake_output import _open_shared
from ._runner import _Child, _split_emitted_lines, _start_child, _tail
from ._verbosity import _effective_timeout

_TAIL_BYTES = 16 * 1024


def _diagnostic(path: str) -> str:
    with _open_shared(path) as stream:
        size = os.fstat(stream.fileno()).st_size
        stream.seek(max(0, size - _TAIL_BYTES))
        return stream.read(_TAIL_BYTES).decode("utf-8", "replace")


def _deliver_lines(
    completion: Future[int],
    log: IO[bytes],
    on_line: Callable[[str], None],
    mirror: bool,
) -> None:
    pending = b""

    def deliver(segments: list[tuple[str, str]]) -> None:
        for text, terminator in segments:
            if completion.done():
                completion.result()  # Stop dispatch immediately on a tool timeout.
            on_line(text)
            if mirror and sys.stdout is not None:
                sys.stdout.write(text + terminator)
                sys.stdout.flush()

    while True:
        done = completion.done()
        end = os.fstat(log.fileno()).st_size
        while log.tell() < end:
            chunk = log.read(min(65536, end - log.tell()))
            segments, pending = _split_emitted_lines(pending + chunk, at_eof=False)
            deliver(segments)
        if done:
            segments, _ = _split_emitted_lines(pending, at_eof=True)
            deliver(segments)
            return
        time.sleep(0.02)


@contextmanager
def _contained(child: _Child) -> Iterator[_Child]:
    try:
        yield child
    except BaseException:
        child.stop()
        raise
    finally:
        if child.proc is not None and child.proc.stdin is not None:
            child.proc.stdin.close()
        child.release()


def _wait_for_build(
    cmd: list[str],
    tool: _Child,
    console: _Child,
    timeout: float | None,
    cancel: threading.Event | None = None,
) -> int:
    deadline = None if timeout is None else time.monotonic() + timeout

    def wait(proc: subprocess.Popen) -> int:
        while proc.poll() is None:
            left = None if deadline is None else deadline - time.monotonic()
            if left is not None and left <= 0:
                assert timeout is not None
                raise subprocess.TimeoutExpired(cmd, timeout)
            if cancel is None:
                try:
                    return proc.wait(timeout=left)
                except subprocess.TimeoutExpired as exc:
                    raise subprocess.TimeoutExpired(
                        cmd, timeout if timeout is not None else exc.timeout
                    ) from None
            if cancel.wait(0.02 if left is None else min(0.02, left)):
                raise CancelledError()
        return proc.returncode

    proc, relay = tool.proc, console.proc
    assert proc is not None and relay is not None and relay.stdin is not None
    try:
        status = wait(proc)
        relay.stdin.write(b"D")
        relay.stdin.flush()
        try:
            relay_status = wait(relay)
        except subprocess.TimeoutExpired:
            if not status:
                raise
            console.stop()
            return status
        if relay_status and not status:
            raise NSXToolchainError(f"Could not forward CMake output (exit code {relay_status}).")
        return status
    except subprocess.TimeoutExpired:
        # The caller might still be in its callback when the deadline expires.
        console.stop()
        tool.stop()
        raise


def run_cmake(
    cmd: list[str], *, context: str, on_line: Callable[[str], None] | None = None
) -> None:
    """Run CMake with live console output and bounded exception diagnostics."""
    timeout = _effective_timeout(None)
    # Read regular files up to the size at completion. A background helper
    # inheriting a tool's console handles cannot hold this read open.
    with ExitStack() as stack:
        out = stack.enter_context(tempfile.NamedTemporaryFile())
        err = None if on_line is not None else stack.enter_context(tempfile.NamedTemporaryFile())
        paths = [out.name] if err is None else [out.name, err.name]
        mirror = on_line is not None and sys.stdout is not sys.__stdout__
        console = stack.enter_context(_contained(_Child()))
        tool = stack.enter_context(_contained(_Child()))
        relay = _start_child(
            console,
            [sys.executable, "-I", "-S", str(Path(__file__).with_name("_cmake_output.py")), *paths],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL if mirror or sys.stdout is None else None,
            stderr=subprocess.DEVNULL if sys.stderr is None else None,
            start_new_session=(os.name != "nt"),
        )
        assert relay.stdin is not None
        _start_child(
            tool,
            cmd,
            stdout=out,
            stderr=err if err is not None else subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        if on_line is None:
            status = _wait_for_build(cmd, tool, console, timeout)
        else:
            # Callbacks stay on the caller's thread. Tool and console deadlines
            # must still be enforced while an embedder is handling a line.
            cancel = threading.Event()
            with _open_shared(out.name) as log, ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    completion = pool.submit(_wait_for_build, cmd, tool, console, timeout, cancel)
                    _deliver_lines(completion, log, on_line, mirror)
                    status = completion.result()
                finally:
                    cancel.set()
        if status:
            output = _diagnostic(out.name)
            errors = _diagnostic(err.name) if err is not None else ""
            cause = subprocess.CalledProcessError(status, cmd, output=output, stderr=errors)
            command = subprocess.list2cmdline(cmd) if os.name == "nt" else shlex.join(cmd)
            message = f"{context} failed with exit code {status}: {command}"
            for text in (output, errors):
                if text:
                    message += f"\n{_tail(text)}"
            raise NSXToolchainError(message) from cause
