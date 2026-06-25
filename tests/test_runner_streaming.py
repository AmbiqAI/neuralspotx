"""Streaming-output behaviour of ``subprocess_utils.run(on_line=...)``.

Covers the ``_split_emitted_lines`` helper (pure) and the live streaming
path that splits on ``\\r``/``\\n``/``\\r\\n`` so carriage-return progress
redraws render in place while the wall-clock timeout is still enforced —
even when a process emits partial output and then hangs without a newline.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from neuralspotx.subprocess_utils import run
from neuralspotx.subprocess_utils._runner import _split_emitted_lines


class TestSplitEmittedLines:
    def test_newline_lines(self) -> None:
        segments, rest = _split_emitted_lines(b"a\nb\n", at_eof=False)
        assert segments == [("a", "\n"), ("b", "\n")]
        assert rest == b""

    def test_carriage_return_progress(self) -> None:
        # The trailing \r is held back (it may begin a \r\n), so only the
        # first complete segment is emitted mid-stream.
        segments, rest = _split_emitted_lines(b"10%\r20%\r", at_eof=False)
        assert segments == [("10%", "\r")]
        assert rest == b"20%\r"

    def test_crlf_treated_as_single_terminator(self) -> None:
        segments, rest = _split_emitted_lines(b"x\r\ny\r\n", at_eof=False)
        assert segments == [("x", "\r\n"), ("y", "\r\n")]
        assert rest == b""

    def test_partial_line_is_held(self) -> None:
        segments, rest = _split_emitted_lines(b"abc", at_eof=False)
        assert segments == []
        assert rest == b"abc"

    def test_trailing_cr_held_until_more_bytes(self) -> None:
        # A bare trailing \r might be the first half of a \r\n, so hold it.
        segments, rest = _split_emitted_lines(b"x\r", at_eof=False)
        assert segments == []
        assert rest == b"x\r"
        # Completing it as \r\n must yield a single CRLF segment.
        segments, rest = _split_emitted_lines(rest + b"\ny", at_eof=False)
        assert segments == [("x", "\r\n")]
        assert rest == b"y"

    def test_trailing_cr_flushed_at_eof(self) -> None:
        segments, rest = _split_emitted_lines(b"x\r", at_eof=True)
        assert segments == [("x", "\r")]
        assert rest == b""

    def test_unterminated_remainder_flushed_at_eof(self) -> None:
        segments, rest = _split_emitted_lines(b"done", at_eof=True)
        assert segments == [("done", "")]
        assert rest == b""

    def test_multibyte_utf8_split_across_reads(self) -> None:
        # "é" is 0xC3 0xA9; a read boundary mid-character must not corrupt it.
        first, rest = _split_emitted_lines(b"a\xc3", at_eof=False)
        assert first == []
        assert rest == b"a\xc3"
        second, rest = _split_emitted_lines(rest + b"\xa9\n", at_eof=False)
        assert second == [("a\u00e9", "\n")]
        assert rest == b""


class TestStreamingRun:
    def test_newlines_streamed_per_line(self, capfd: pytest.CaptureFixture[str]) -> None:
        lines: list[str] = []
        run(
            [sys.executable, "-c", "print('0'); print('1'); print('2')"],
            on_line=lines.append,
        )
        assert lines == ["0", "1", "2"]
        out, _ = capfd.readouterr()
        if os.name != "nt":
            # Windows translates \n -> \r\n at the fd level; the portable
            # guarantee is the per-line on_line split asserted above.
            assert out == "0\n1\n2\n"

    def test_carriage_return_progress_preserved(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        lines: list[str] = []
        run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('10%\\r20%\\r30%\\n')",
            ],
            on_line=lines.append,
        )
        assert lines == ["10%", "20%", "30%"]
        out, _ = capfd.readouterr()
        if os.name != "nt":
            # The bare \r terminators are preserved so a terminal redraws in
            # place. (Windows translates \n at the fd level, so the exact
            # byte stream isn't portable; the on_line split above is.)
            assert out == "10%\r20%\r30%\n"

    def test_timeout_with_no_output(self) -> None:
        with pytest.raises(subprocess.TimeoutExpired):
            run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                on_line=lambda _line: None,
                timeout=1.0,
            )

    def test_timeout_after_partial_unterminated_output(self) -> None:
        # The key guarantee: a process that prints without a trailing
        # newline and then hangs must still hit the wall-clock budget.
        with pytest.raises(subprocess.TimeoutExpired):
            run(
                [
                    sys.executable,
                    "-c",
                    "import sys, time; sys.stdout.write('partial'); "
                    "sys.stdout.flush(); time.sleep(30)",
                ],
                on_line=lambda _line: None,
                timeout=1.0,
            )
