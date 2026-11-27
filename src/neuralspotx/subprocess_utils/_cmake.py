"""Run a CMake command with live console output and diagnostics for Python callers."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
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
    completion: Future[int],
    log: IO[bytes],
    on_line: Callable[[str], None],
    mirror: bool,
) -> None:
    pending = b""

    def deliver(segments: list[tuple[str, str]]) -> None:
        for text, terminator in segments:
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


def _execute(
    cmd: list[str],
    out: IO[bytes],
    err: IO[bytes] | None,
    paths: list[str],
    timeout: float | None,
    mirror: bool,
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

    relay_child = _Child()
    child = _Child()
    try:
        relay = _start_child(
            relay_child,
            [sys.executable, "-I", "-S", str(Path(__file__).with_name("_cmake_output.py")), *paths],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL if mirror or sys.stdout is None else None,
            stderr=subprocess.DEVNULL if sys.stderr is None else None,
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
        status = wait(proc)
        relay.stdin.close()
        try:
            relay_status = wait(relay)
        except subprocess.TimeoutExpired:
            if not status:
                raise
            relay_child.stop()
            return status
        if relay_status and not status:
            raise NSXToolchainError(f"Could not forward CMake output (exit code {relay_status}).")
        return status
    except BaseException:
        relay_child.stop()
        child.stop()
        raise
    finally:
        if relay_child.proc is not None and relay_child.proc.stdin is not None:
            relay_child.proc.stdin.close()
        relay_child.release()
        child.release()


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
        if on_line is None:
            status = _execute(
                cmd, out.file, err.file if err is not None else None, paths, timeout, False
            )
        else:
            # Callbacks stay on the caller's thread. Tool and console deadlines
            # must still be enforced while an embedder is handling a line.
            mirror = sys.stdout is not sys.__stdout__
            cancel = threading.Event()
            with _open_shared(out.name) as log, ThreadPoolExecutor(max_workers=1) as pool:
                completion = pool.submit(
                    _execute, cmd, out.file, None, paths, timeout, mirror, cancel
                )
                try:
                    _deliver_lines(completion, log, on_line, mirror)
                finally:
                    cancel.set()
                status = completion.result()
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
