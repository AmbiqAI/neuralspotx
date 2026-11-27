"""OS-level regressions in CMake output capture, independent of an installed SDK."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from neuralspotx import NSXTimeoutError, NSXToolchainError
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


@pytest.mark.parametrize("mode", ["nonzero", "timeout", "callback"])
def test_retained_failures_release_files(mode):
    if os.name == "nt":
        import ctypes

        def count():
            value = ctypes.c_ulong()
            kernel = ctypes.windll.kernel32
            if not kernel.GetProcessHandleCount(ctypes.c_void_p(-1), ctypes.byref(value)):
                raise ctypes.WinError()
            return value.value

    elif Path("/proc/self/fd").is_dir():

        def count():
            return len(os.listdir("/proc/self/fd"))

    else:
        pytest.skip("requires Windows handle or Linux file descriptor accounting")

    def reject_line(_):
        raise ValueError("callback failed")

    tool = (
        "raise SystemExit(3)"
        if mode == "nonzero"
        else ("import time; print('ready', flush=True); time.sleep(15)")
    )
    expected = {"nonzero": NSXToolchainError, "timeout": NSXTimeoutError, "callback": ValueError}
    baseline = count()
    failures = []
    for _ in range(6):
        with (
            pytest.raises(expected[mode]) as error,
            timeout_budget(0.3 if mode == "timeout" else 5),
        ):
            run_cmake(
                [sys.executable, "-c", tool],
                context="CMake",
                on_line=reject_line if mode == "callback" else None,
            )
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
@pytest.mark.parametrize("redirect", [False, True])
def test_relay_failure_keeps_tool_status_and_releases_processes(redirect):
    script = """
import contextlib, sys
from neuralspotx import NSXToolchainError
from neuralspotx.subprocess_utils._cmake import run_cmake
from neuralspotx.subprocess_utils._runner import _LIVE
try:
    with contextlib.ExitStack() as stack:
        callback = None
        if sys.argv[1] == "True":
            sink = stack.enter_context(open("/dev/full", "w"))
            stack.enter_context(contextlib.redirect_stdout(sink))
            callback = lambda line: None
        run_cmake([sys.executable, "-c", "import time; print('progress', flush=True); time.sleep(.5); raise SystemExit(17)"], context="CMake", on_line=callback)
except NSXToolchainError as exc:
    assert exc.__cause__.returncode == 17
    assert not _LIVE
else:
    raise AssertionError("expected tool failure")
"""
    with open("/dev/full", "wb") as sink:
        result = subprocess.run(
            [sys.executable, "-c", script, str(redirect)],
            stdout=sink,
            stderr=subprocess.PIPE,
            timeout=8,
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


@pytest.mark.parametrize("status", [0, 23])
def test_python_output_error_preserves_tool_result(status):
    import contextlib
    import io

    class FailedOutput(io.StringIO):
        def write(self, text):
            raise OSError("console unavailable")

    lines = []
    with contextlib.redirect_stdout(FailedOutput()), pytest.raises(NSXToolchainError) as failure:
        run_cmake(
            [sys.executable, "-c", f"print('build output'); raise SystemExit({status})"],
            context="CMake",
            on_line=lines.append,
        )
    assert lines == ["build output"]
    cause = failure.value.__cause__
    if status:
        assert isinstance(cause, subprocess.CalledProcessError) and cause.returncode == status
        assert "build output" in str(failure.value)
    else:
        assert isinstance(cause, OSError) and "console unavailable" in str(failure.value)


def test_strict_console_encoding_preserves_tool_error_without_traceback(capfd):
    import contextlib

    reader, writer = os.pipe()
    lines = []
    with os.fdopen(reader, "rb"), os.fdopen(writer, "w", encoding="ascii") as sink:
        with contextlib.redirect_stdout(sink), pytest.raises(NSXToolchainError) as error:
            run_cmake(
                [
                    sys.executable,
                    "-c",
                    "import os; os.write(1, bytes([195,169,10])); raise SystemExit(37)",
                ],
                context="CMake",
                on_line=lines.append,
            )
    assert isinstance(error.value.__cause__, subprocess.CalledProcessError)
    assert error.value.__cause__.returncode == 37
    assert lines == ["\u00e9"]
    stderr = capfd.readouterr().err
    assert "Could not forward CMake output" in stderr
    assert "Traceback" not in stderr


def test_relay_encoding_error_delivers_pending_callbacks():
    import contextlib
    import time

    reader, writer = os.pipe()
    lines = []

    def receive(line):
        if not lines:
            time.sleep(0.2)
        lines.append(line)

    with os.fdopen(reader, "rb"), os.fdopen(writer, "w", encoding="ascii") as sink:
        with contextlib.redirect_stdout(sink), pytest.raises(NSXToolchainError, match="forward"):
            run_cmake(
                [sys.executable, "-c", "import os; os.write(1, bytes([195,169,10])*64)"],
                context="CMake",
                on_line=receive,
            )
    assert lines == ["\u00e9"] * 64
