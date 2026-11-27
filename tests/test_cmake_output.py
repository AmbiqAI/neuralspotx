"""OS-level regressions in CMake output capture, independent of an installed SDK."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from neuralspotx import NSXToolchainError
from neuralspotx.subprocess_utils import timeout_budget
from neuralspotx.subprocess_utils._cmake import run_cmake


def test_full_console_pipe_keeps_timeout():
    script = """
import sys
from neuralspotx import NSXTimeoutError
from neuralspotx.subprocess_utils import timeout_budget
from neuralspotx.subprocess_utils._cmake import run_cmake
try:
    with timeout_budget(0.5):
        run_cmake([sys.executable, "-c", "print('A' * 2000000)"], context="CMake")
except NSXTimeoutError:
    sys.exit(0)
sys.exit(1)
"""
    # Keep the read end open and deliberately don't consume it during wait().
    with subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE) as proc:
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
