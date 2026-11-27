"""Follow the two build logs on the inherited console, isolated from the tool deadline."""

from __future__ import annotations

import codecs
import io
import os
import sys
import threading
from contextlib import ExitStack, suppress
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
        encoding, errors, *paths = sys.argv[1:]
        logs = [stack.enter_context(_open_shared(path)) for path in paths]
        decoder = None
        if encoding and isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding=encoding, errors=errors, newline="")
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
        outputs = [sys.stdout, sys.stderr][: len(logs)]
        while True:
            done = finished.is_set()
            sizes = [os.fstat(log.fileno()).st_size for log in logs]
            for index, (log, size) in enumerate(zip(logs, sizes, strict=True)):
                output = outputs[index]
                if output is None:
                    log.seek(size)
                    continue
                try:
                    while log.tell() < size:
                        chunk = log.read(min(65536, size - log.tell()))
                        if not chunk:
                            break
                        if decoder is None:
                            data = memoryview(chunk)
                            while data:
                                data = data[os.write(output.fileno(), data) :]
                        else:
                            output.write(decoder.decode(chunk))
                            output.flush()
                    if done and decoder is not None:
                        output.write(decoder.decode(b"", final=True))
                        output.flush()
                except BrokenPipeError:
                    # The downstream consumer closed. Discard future bytes and
                    # any pending text-wrapper flush during interpreter shutdown.
                    with open(os.devnull, "wb") as sink:
                        os.dup2(sink.fileno(), output.fileno())
                    outputs[index] = None
            if done:
                return
            finished.wait(0.02)


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        with suppress(OSError):
            os.write(2, f"Could not forward CMake output: {exc}\n".encode("utf-8", "replace"))
        os._exit(1)  # The failed output stream cannot be flushed at shutdown.
