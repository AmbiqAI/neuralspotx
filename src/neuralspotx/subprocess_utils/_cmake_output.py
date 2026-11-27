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
        if os.read(0, 1) == b"D":
            finished.set()
            os.read(0, 1)
        # The parent keeps the control pipe open through the final drain.
        # EOF also terminates a relay blocked writing to an abandoned console.
        os._exit(0)

    threading.Thread(target=wait_for_parent, daemon=True).start()
    with ExitStack() as stack:
        logs = [stack.enter_context(_open_shared(path)) for path in sys.argv[1:]]
        outputs = [sys.stdout, sys.stderr][: len(logs)]
        while True:
            done = finished.is_set()
            sizes = [os.fstat(log.fileno()).st_size for log in logs]
            for index, (log, size) in enumerate(zip(logs, sizes, strict=True)):
                while log.tell() < size:
                    chunk = log.read(min(65536, size - log.tell()))
                    if not chunk:
                        break
                    output = outputs[index]
                    if output is not None:
                        try:
                            data = memoryview(chunk)
                            while data:
                                data = data[os.write(output.fileno(), data) :]
                        except BrokenPipeError:
                            # A consumer such as head has finished with this stream.
                            outputs[index] = None
            if done:
                return
            finished.wait(0.02)


if __name__ == "__main__":
    main()
