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
