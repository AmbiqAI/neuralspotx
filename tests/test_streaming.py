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
