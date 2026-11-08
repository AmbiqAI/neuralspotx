"""Bounded parent-side RTT worker supervision and byte delivery."""

from __future__ import annotations

import base64
import binascii
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

from ._errors import NSXConfigError, NSXError
from .models._rtt import RttResult, RttSettings
from .subprocess_utils import die_with_parent_preexec
from .subprocess_utils._runner import _Child, _start_child

_SHUTDOWN_GRACE_S = 3.0


def _worker_command(settings: RttSettings, duration_s: float) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "neuralspotx._rtt_worker",
        "--device",
        settings.device,
        "--speed",
        str(settings.speed_khz),
        "--address",
        str(settings.address),
        "--duration",
        str(duration_s),
    ]
    if settings.probe_serial is not None:
        cmd.extend(["--serial", settings.probe_serial])
    return cmd


def _pump(stream: BinaryIO, messages: queue.Queue[bytes], stop: threading.Event) -> None:
    while not stop.is_set():
        line = stream.readline(8193)
        while not stop.is_set():
            try:
                messages.put(line, timeout=0.05)
                break
            except queue.Full:
                continue
        if not line or len(line) > 8192:
            return


def _decode_payload(payload: bytes) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except binascii.Error as exc:
        raise NSXError("Invalid RTT worker payload.") from exc


def capture_rtt(
    settings: RttSettings,
    *,
    duration_s: float,
    startup_timeout_s: float,
    capture: Path | None,
    on_data: Callable[[bytes], None] | None,
) -> RttResult:
    """Contain native operations; preserve partial output when a capture fails.

    Sink writes and callbacks execute synchronously and must return promptly.
    Startup and capture bounds apply to the worker, not arbitrary caller code.
    """
    sink: BinaryIO | None = None
    if capture is not None:
        capture = capture.expanduser().resolve()
        if capture == settings.elf or (capture.exists() and capture.samefile(settings.elf)):
            raise NSXConfigError("RTT capture file must not overwrite the input ELF.")
        try:
            # Exclusive creation avoids destroying an existing app/input file.
            sink = capture.open("xb")
        except OSError as exc:
            raise NSXConfigError(
                f"Cannot create RTT capture {capture}: {exc}. Choose a new file."
            ) from exc
    child = _Child()
    messages: queue.Queue[bytes] = queue.Queue(maxsize=16)
    stop = threading.Event()
    reader: threading.Thread | None = None
    ready = False
    count = 0
    deadline = time.monotonic() + startup_timeout_s
    try:
        proc = _start_child(
            child,
            _worker_command(settings, duration_s),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=die_with_parent_preexec(),
        )
        assert proc.stdout is not None
        reader = threading.Thread(target=_pump, args=(proc.stdout, messages, stop), daemon=True)
        reader.start()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                phase = (
                    "capture/shutdown" if ready else "startup (probe connection/channel readiness)"
                )
                raise NSXError(
                    f"RTT {phase} timed out; stopping the worker. Partial output is retained."
                )
            try:
                line = messages.get(timeout=remaining)
            except queue.Empty:
                continue
            if not line:
                raise NSXError(
                    "RTT worker exited without completing capture. Check SEGGER J-Link installation and probe availability."
                )
            if len(line) > 8192 or not line.endswith(b"\n"):
                raise NSXError("Invalid RTT worker response.")
            kind, sep, payload = line.removesuffix(b"\n").removesuffix(b"\r").partition(b"\t")
            if not sep:
                raise NSXError("Invalid RTT worker response.")
            if kind == b"ready" and not ready:
                try:
                    serial = payload.decode("ascii")
                except UnicodeError as exc:
                    raise NSXError("Invalid RTT worker probe serial.") from exc
                if not serial.isdecimal() or int(serial) <= 0:
                    raise NSXError("Invalid RTT worker probe serial.")
                settings = replace(settings, probe_serial=serial)
                ready = True
                deadline = time.monotonic() + duration_s + _SHUTDOWN_GRACE_S
            elif kind == b"data" and ready:
                data = _decode_payload(payload)
                if sink is not None:
                    try:
                        sink.write(data)
                        sink.flush()
                    except OSError as exc:
                        raise NSXError(
                            f"RTT file write failed: {exc}. Partial output is retained."
                        ) from exc
                if on_data is not None:
                    on_data(data)
                count += len(data)
            elif kind == b"error":
                message = _decode_payload(payload).decode("utf-8", "replace")
                raise NSXError(f"RTT capture failed: {message}")
            elif kind == b"done" and ready:
                try:
                    status = proc.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired as exc:
                    raise NSXError("RTT worker did not exit after cleanup.") from exc
                if status:
                    raise NSXError(f"RTT worker exited with status {status}.")
                return RttResult(settings, count, capture)
            else:
                raise NSXError("Unexpected RTT worker response.")
    finally:
        stop.set()
        try:
            child.stop()
        finally:
            child.release()
            if reader is not None:
                reader.join(timeout=1)
            if child.proc is not None and child.proc.stdout is not None:
                child.proc.stdout.close()
            if sink is not None:
                sink.close()
