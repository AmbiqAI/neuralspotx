"""Verify that ``run`` / ``run_capture`` reap the entire process tree.

This is the regression test for REVIEW2 item B1.  On POSIX the guarantee
comes from ``start_new_session=True`` + ``killpg``; on Windows it comes
from a Win32 Job Object with ``KILL_ON_JOB_CLOSE``.  Both code paths are
exercised here by spawning a Python parent that spawns a long-lived
Python grandchild and writes the grandchild's PID to a file.  After the
parent is killed via the timeout path, the grandchild must also be dead.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from textwrap import dedent

import pytest

from neuralspotx.subprocess_utils import run, run_capture


def _grandchild_is_alive(pid: int) -> bool:
    """Return True if *pid* still exists (cross-platform)."""
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
        # ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)`` is
        # the no-rights-needed probe; if it returns a handle the process
        # still exists.  Falling back to ``tasklist`` keeps the test
        # tolerant on stripped-down runners.
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_pid_file(path: Path, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return int(text)
        time.sleep(0.05)
    raise AssertionError(f"grandchild PID file {path} never appeared")


def _wait_for_pid_to_die(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _grandchild_is_alive(pid):
            return True
        time.sleep(0.1)
    return False


def _spawner_script(pid_file: Path) -> str:
    """Python source that spawns a long-lived grandchild and writes its PID."""
    return dedent(
        f"""
        import os, subprocess, sys, time
        pid_file = {str(pid_file)!r}
        # Sleep a long time; parent will be killed via timeout, and the
        # process-tree teardown must reap us too.
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(120)"]
        )
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(str(child.pid))
            fh.flush()
            os.fsync(fh.fileno())
        # Block here so the parent wait() actually times out.
        time.sleep(120)
        """
    )


@pytest.mark.parametrize("runner", [run, run_capture], ids=["run", "run_capture"])
def test_timeout_reaps_grandchild(tmp_path: Path, runner) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "spawner.py"
    script.write_text(_spawner_script(pid_file), encoding="utf-8")

    with pytest.raises(subprocess.TimeoutExpired):
        runner([sys.executable, str(script)], timeout=1.5)

    grandchild_pid = _wait_for_pid_file(pid_file)
    assert _wait_for_pid_to_die(grandchild_pid), (
        f"grandchild pid={grandchild_pid} survived process-tree teardown "
        f"(B1 regression: Windows Job Object / POSIX killpg failed to reap it)"
    )
