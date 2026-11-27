"""Drain child pipes while the calling thread delivers output and enforces the deadline."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO


@contextmanager
def output_chunks(
    streams: list[IO[bytes]], cmd: list[str], timeout: float | None, deadline: float | None
) -> Iterator[Iterator[tuple[int, bytes]]]:
    """Yield indexed chunks, including one empty chunk per stream at EOF."""
    messages: queue.Queue[tuple[int, bytes | OSError]] = queue.Queue(maxsize=8)
    stop = threading.Event()

    def drain(index: int, stream: IO[bytes]) -> None:
        while not stop.is_set():
            try:
                item = os.read(stream.fileno(), 65536)
            except OSError as exc:
                item = exc
            while not stop.is_set():
                try:
                    messages.put((index, item), timeout=0.1)
                    break
                except queue.Full:
                    continue
            if not item or isinstance(item, OSError):
                return

    def consume() -> Iterator[tuple[int, bytes]]:
        open_streams = len(streams)
        while open_streams:
            remaining = None if deadline is None else deadline - time.monotonic()
            try:
                if remaining is not None and remaining <= 0:
                    raise queue.Empty
                index, item = messages.get(timeout=remaining)
            except queue.Empty:
                assert timeout is not None
                raise subprocess.TimeoutExpired(cmd, timeout) from None
            if isinstance(item, OSError):
                raise item
            if not item:
                open_streams -= 1
            yield index, item

    try:
        for index, stream in enumerate(streams):
            threading.Thread(target=drain, args=(index, stream), daemon=True).start()
        yield consume()
    finally:
        stop.set()
