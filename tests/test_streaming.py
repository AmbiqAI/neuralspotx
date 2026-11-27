"""Phase 4: subprocess line streaming via on_line callback."""

from __future__ import annotations

import sys

import pytest

from neuralspotx.subprocess_utils import run


def test_run_streams_lines_in_order(capfd: pytest.CaptureFixture[str]) -> None:
    captured: list[str] = []
    run(
        [
            sys.executable,
            "-c",
            "import sys\nfor i in range(5):\n    print(f'line-{i}', flush=True)",
        ],
        on_line=captured.append,
    )
    assert captured == [f"line-{i}" for i in range(5)]
    # Lines are also re-emitted on the parent's stdout for user visibility.
    out, _err = capfd.readouterr()
    for i in range(5):
        assert f"line-{i}" in out


def test_run_merges_stderr_into_on_line() -> None:
    captured: list[str] = []
    run(
        [
            sys.executable,
            "-c",
            "import sys\nprint('to-stdout', flush=True)\nprint('to-stderr', file=sys.stderr, flush=True)",
        ],
        on_line=captured.append,
    )
    assert "to-stdout" in captured
    assert "to-stderr" in captured


def test_run_propagates_nonzero_exit_with_on_line() -> None:
    import subprocess

    captured: list[str] = []
    with pytest.raises(subprocess.CalledProcessError):
        run(
            [sys.executable, "-c", "print('hi'); raise SystemExit(3)"],
            on_line=captured.append,
        )
    assert "hi" in captured


def test_run_enforces_timeout_when_streaming_child_hangs_without_output() -> None:
    """A child that never produces newlines must still hit the timeout."""
    import subprocess

    if sys.platform.startswith("win"):
        pytest.skip("Windows pipe select() not supported by stdlib select.select")

    captured: list[str] = []
    with pytest.raises(subprocess.TimeoutExpired):
        run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.5,
            on_line=captured.append,
        )


def test_run_terminates_child_when_on_line_callback_raises() -> None:
    """If on_line() raises, the subprocess tree must be torn down."""

    class Boom(Exception):
        pass

    def callback(_line: str) -> None:
        raise Boom

    with pytest.raises(Boom):
        run(
            [
                sys.executable,
                "-c",
                "import sys, time\nprint('first', flush=True)\ntime.sleep(30)",
            ],
            timeout=5.0,
            on_line=callback,
        )
