"""Follow the two build logs on the inherited console, isolated from the tool deadline."""

from __future__ import annotations

import os
import sys
import threading
from contextlib import ExitStack
from typing import IO


def _open_shared(path: str) -> IO[bytes]:
    # The creator's NamedTemporaryFile uses delete-on-close on Windows.
    return open(
        path, "rb", opener=lambda p, flags: os.open(p, flags | getattr(os, "O_TEMPORARY", 0))
    )


def main() -> None:
    finished = threading.Event()

    def wait_for_parent() -> None:
        sys.stdin.buffer.read()
        finished.set()

    threading.Thread(target=wait_for_parent, daemon=True).start()
    with ExitStack() as stack:
        logs = [stack.enter_context(_open_shared(path)) for path in sys.argv[1:]]
        outputs = (sys.stdout, sys.stderr)[: len(logs)]
        while True:
            done = finished.is_set()
            sizes = [os.fstat(log.fileno()).st_size for log in logs]
            for log, size, output in zip(logs, sizes, outputs, strict=True):
                while log.tell() < size:
                    chunk = log.read(min(65536, size - log.tell()))
                    if not chunk:
                        break
                    if output is not None:
                        output.buffer.write(chunk)
                        output.buffer.flush()
            if done:
                return
            finished.wait(0.02)


if __name__ == "__main__":
    main()
