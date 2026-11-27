"""OS-level regressions in CMake output capture, independent of an installed SDK."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from neuralspotx import NSXToolchainError
from neuralspotx.subprocess_utils import timeout_budget
from neuralspotx.subprocess_utils._cmake import run_cmake


@pytest.mark.parametrize("exit_status", [0, 17])
def test_full_console_pipe_keeps_timeout(exit_status):
    script = """
import sys
from neuralspotx import NSXTimeoutError, NSXToolchainError
from neuralspotx.subprocess_utils import timeout_budget
from neuralspotx.subprocess_utils._cmake import run_cmake
try:
    with timeout_budget(0.5):
        run_cmake([sys.executable, "-c", "print('A' * 2000000); raise SystemExit(" + sys.argv[1] + ")"], context="CMake")
except NSXTimeoutError:
    sys.exit(0 if sys.argv[1] == "0" else 1)
except NSXToolchainError as exc:
    sys.exit(0 if sys.argv[1] == "17" and exc.__cause__.returncode == 17 else 1)
sys.exit(1)
"""
    # Keep the read end open and deliberately don't consume it during wait().
    with subprocess.Popen(
        [sys.executable, "-c", script, str(exit_status)], stdout=subprocess.PIPE
    ) as proc:
        try:
            assert proc.wait(timeout=8) == 0
        finally:
            proc.kill()


@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="Linux FD accounting")
def test_retained_failures_release_files():
    def count():
        return len(os.listdir("/proc/self/fd"))

    baseline = count()
    failures = []
    for _ in range(6):
        with pytest.raises(NSXToolchainError) as error:
            run_cmake([sys.executable, "-c", "raise SystemExit(3)"], context="CMake")
        failures.append(error.value)
    assert count() <= baseline + 1


def test_tool_finishes_when_detached_helper_inherits_output(tmp_path):
    # Bound the helper's lifetime even if the assertion fails.
    sentinel = tmp_path / "stop"
    helper = (
        "import os,time,sys; deadline=time.monotonic()+8\n"
        "while not os.path.exists(sys.argv[1]) and time.monotonic() < deadline: time.sleep(.05)"
    )
    command = [
        sys.executable,
        "-c",
        "import subprocess,sys; subprocess.Popen(sys.argv[1:], start_new_session=True)",
        sys.executable,
        "-c",
        helper,
        str(sentinel),
    ]
    try:
        with timeout_budget(3):
            run_cmake(command, context="CMake")
    finally:
        sentinel.touch()


def test_closed_console_pipe_preserves_tool_success():
    script = """
import sys
from neuralspotx.subprocess_utils._cmake import run_cmake
run_cmake([sys.executable, "-c", "print('x' * 2000000)"], context="CMake")
"""
    with subprocess.Popen(
        [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        proc.stdout.close()
        try:
            assert proc.wait(timeout=8) == 0, proc.stderr.read()
            assert b"Traceback" not in proc.stderr.read()
        finally:
            proc.kill()


def test_callback_mirrors_to_redirected_python_stream():
    import contextlib
    import io

    capture = io.StringIO()
    lines = []
    with contextlib.redirect_stdout(capture):
        run_cmake([sys.executable, "-c", "print('hello')"], context="CMake", on_line=lines.append)
    assert lines == ["hello"]
    assert capture.getvalue().splitlines() == ["hello"]


def test_slow_callback_preserves_completed_tool_failure():
    import time

    lines = []

    def receive(line):
        if not lines:
            time.sleep(0.8)
        lines.append(line)

    with pytest.raises(NSXToolchainError) as error, timeout_budget(0.5):
        run_cmake(
            [sys.executable, "-c", "print('a'*65536); print('diagnostic'); raise SystemExit(17)"],
            context="CMake",
            on_line=receive,
        )
    assert isinstance(error.value.__cause__, subprocess.CalledProcessError)
    assert error.value.__cause__.returncode == 17
    assert lines[-1] == "diagnostic"


def test_timeout_stops_dispatching_queued_lines():
    import time

    from neuralspotx import NSXTimeoutError

    lines = []

    def slow(line):
        lines.append(line)
        time.sleep(1.2)

    with pytest.raises(NSXTimeoutError), timeout_budget(0.6):
        run_cmake(
            [sys.executable, "-c", "import time; print('a\\nb', flush=True); time.sleep(8)"],
            context="CMake",
            on_line=slow,
        )
    assert lines == ["a"]


@pytest.mark.skipif(not Path("/dev/full").exists(), reason="requires a failing output device")
def test_relay_failure_keeps_tool_status_and_releases_processes():
    script = """
import sys
from neuralspotx import NSXToolchainError
from neuralspotx.subprocess_utils._cmake import run_cmake
from neuralspotx.subprocess_utils._runner import _LIVE
try:
    run_cmake([sys.executable, "-c", "import time; print('progress', flush=True); time.sleep(.5); raise SystemExit(17)"], context="CMake")
except NSXToolchainError as exc:
    assert exc.__cause__.returncode == 17
    assert not _LIVE
else:
    raise AssertionError("expected tool failure")
"""
    with open("/dev/full", "wb") as sink:
        result = subprocess.run(
            [sys.executable, "-c", script], stdout=sink, stderr=subprocess.PIPE, timeout=8
        )
    assert result.returncode == 0, result.stderr
    assert b"Traceback" not in result.stderr


def test_redirected_full_pipe_with_callback_keeps_timeout():
    script = """
import contextlib, os, sys
from neuralspotx import NSXTimeoutError
from neuralspotx.subprocess_utils import timeout_budget
from neuralspotx.subprocess_utils._cmake import run_cmake
reader, writer = os.pipe()
with os.fdopen(reader, "rb"), os.fdopen(writer, "w") as sink, contextlib.redirect_stdout(sink):
    try:
        with timeout_budget(.7):
            run_cmake([sys.executable, "-c", "for i in range(1000): print('A'*1000)"],
                      context="CMake", on_line=lambda line: None)
    except NSXTimeoutError:
        sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=8)
    assert result.returncode == 0, result.stderr


def test_callback_supports_a_write_only_python_sink():
    import contextlib

    class Sink:
        def __init__(self):
            self.text = ""

        def write(self, text):
            self.text += text

        def flush(self):
            pass

    sink = Sink()
    lines = []
    with contextlib.redirect_stdout(sink):
        run_cmake([sys.executable, "-c", "print('hello')"], context="CMake", on_line=lines.append)
    assert sink.text.splitlines() == lines == ["hello"]


def test_callback_preserves_native_pipe_encoding():
    import contextlib

    reader, writer = os.pipe()
    lines = []
    with os.fdopen(reader, "rb") as source:
        with os.fdopen(writer, "w", encoding="utf-16-le") as sink, contextlib.redirect_stdout(sink):
            run_cmake(
                [sys.executable, "-c", "print('hello')"], context="CMake", on_line=lines.append
            )
        assert source.read().decode("utf-16-le").splitlines() == lines == ["hello"]
