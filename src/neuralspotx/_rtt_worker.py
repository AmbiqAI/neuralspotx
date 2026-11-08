"""Private process boundary around SEGGER's blocking native RTT calls.

stdout is a small line protocol, separated from native SDK diagnostics at the
file-descriptor level. This module is not a supported user command.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from collections.abc import Callable

from .tooling import list_jlink_probes


def _select_serial(serial: str | None) -> str:
    if serial is not None:
        return serial
    probes = list_jlink_probes()
    if len(probes) != 1:
        raise RuntimeError(
            f"Found {len(probes)} J-Link probes; use `nsx probes` and pass --probe-serial."
        )
    return probes[0].serial


def _capture(args: argparse.Namespace, send: Callable[[str, str], None]) -> None:
    try:
        import pylink  # ty: ignore[unresolved-import]  # Optional rtt extra; diagnosed below at runtime.
    except ImportError as exc:
        raise RuntimeError(
            "RTT needs pylink-square. Install `neuralspotx[rtt]`, or run "
            "`pipx inject neuralspotx pylink-square`. Also install SEGGER J-Link Software."
        ) from exc

    serial = _select_serial(args.serial)
    if not serial.isascii() or not serial.isdecimal() or int(serial) <= 0:
        raise RuntimeError("J-Link returned an invalid USB serial number.")
    link = pylink.JLink()
    started = False
    try:
        link.open(serial_no=int(serial))
        link.set_tif(pylink.enums.JLinkInterfaces.SWD)
        link.connect(args.device, speed=args.speed)
        link.rtt_start(block_address=args.address)
        started = True
        while True:
            try:
                if link.rtt_get_num_up_buffers() > 0:
                    descriptor = link.rtt_get_buf_descriptor(0, True)
                    if descriptor.SizeOfBuffer > 0:
                        break
            except pylink.errors.JLinkRTTException:
                # RTT discovery is asynchronous, including firmware initialization.
                pass
            time.sleep(0.02)
        send("ready", serial)
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            data = bytes(link.rtt_read(0, 4096))
            if data:
                send("data", base64.b64encode(data).decode("ascii"))
            else:
                time.sleep(0.02)
    finally:
        try:
            if started:
                link.rtt_stop()
        finally:
            link.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--speed", required=True, type=int)
    parser.add_argument("--address", required=True, type=int)
    parser.add_argument("--duration", required=True, type=float)
    parser.add_argument("--serial")
    args = parser.parse_args()
    # Preserve the protocol pipe while diverting Python and native SDK output.
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="ascii", buffering=1) as protocol:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

        def send(kind: str, payload: str = "") -> None:
            protocol.write(f"{kind}\t{payload}\n")
            protocol.flush()

        try:
            _capture(args, send)
        except Exception as exc:  # worker boundary: turn dependency/SDK failures into diagnostics
            message = f"{type(exc).__name__}: {exc}"[:3000]
            send("error", base64.b64encode(message.encode("utf-8")).decode("ascii"))
            return 1
        send("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
