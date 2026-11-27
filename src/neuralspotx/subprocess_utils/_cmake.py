"""Run a CMake command with live console output and diagnostics for Python callers."""

from __future__ import annotations

import io
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, suppress
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
    pending = bytearray()

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
            if completion.done():
                completion.result()
            chunk = log.read(min(65536, end - log.tell()))
            trailing_cr = pending.endswith(b"\r")
            pending.extend(chunk)
            if not trailing_cr and b"\n" not in chunk and b"\r" not in chunk:
                continue
            segments, rest = _split_emitted_lines(bytes(pending), at_eof=False)
            pending = bytearray(rest)
            deliver(segments)
        if done:
            segments, _ = _split_emitted_lines(bytes(pending), at_eof=True)
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
        try:
            if child.proc is not None and child.proc.stdin is not None:
                with suppress(BrokenPipeError):
                    child.proc.stdin.close()
        finally:
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
        with suppress(BrokenPipeError):
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


def _console_stdout(streaming: bool) -> tuple[int | None, bool]:
    """Keep Python redirection semantics while isolating backpressure from native pipes."""
    if sys.stdout is None:
        return subprocess.DEVNULL, False
    if not streaming or sys.stdout is sys.__stdout__:
        return None, False
    if not isinstance(sys.stdout, io.TextIOWrapper):
        return subprocess.DEVNULL, True
    try:
        fd = sys.stdout.fileno()
        mode = os.fstat(fd).st_mode
    except (OSError, ValueError):
        pass  # In-memory and notebook streams receive text on the caller thread.
    else:
        if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or stat.S_ISCHR(mode):
            return fd, False
    return subprocess.DEVNULL, True


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
        console_stdout, mirror = _console_stdout(on_line is not None)
        console = stack.enter_context(_contained(_Child()))
        tool = stack.enter_context(_contained(_Child()))
        text_console = on_line is not None and not mirror and sys.stdout is not None
        encoding = sys.stdout.encoding if text_console else ""
        errors = (sys.stdout.errors or "strict") if text_console else ""
        relay = _start_child(
            console,
            [
                sys.executable,
                "-I",
                "-S",
                str(Path(__file__).with_name("_cmake_output.py")),
                encoding,
                errors,
                *paths,
            ],
            stdin=subprocess.PIPE,
            stdout=console_stdout,
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
