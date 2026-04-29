#!/usr/bin/env python3
"""Minimal RTT capture for the NSX CoreMark example.

Uses pylink (J-Link Python bindings) to attach to AP510NFA-CBR, locate the
RTT control block at an explicitly-supplied SRAM address, and dump up-buffer
0 to stdout / a file until the user hits Ctrl-C or the timeout elapses.

Usage:
    python rtt_capture.py --rtt-addr 0x2000d350 --duration 25 --out /tmp/cm.log
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pylink


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="AP510NFA-CBR")
    p.add_argument("--speed", type=int, default=4000)
    p.add_argument(
        "--rtt-addr",
        type=lambda s: int(s, 0),
        required=True,
        help="Address of the SEGGER RTT control block (e.g. 0x2000d350)",
    )
    p.add_argument("--duration", type=float, default=25.0)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    jlink = pylink.JLink()
    jlink.open()
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(args.device, speed=args.speed)

    jlink.rtt_start(block_address=args.rtt_addr)

    # rtt_start is async — wait for the J-Link to confirm the control block
    # has been located before issuing rtt_get_num_up_buffers.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            if jlink.rtt_get_num_up_buffers() >= 1:
                break
        except pylink.errors.JLinkRTTException:
            pass
        time.sleep(0.05)
    else:
        print("ERROR: RTT control block not located", file=sys.stderr)
        return 1

    out_fh = args.out.open("w") if args.out else None
    sink = out_fh or sys.stdout

    end = time.monotonic() + args.duration
    try:
        while time.monotonic() < end:
            data = jlink.rtt_read(0, 4096)
            if data:
                sink.write(bytes(data).decode("utf-8", errors="replace"))
                sink.flush()
            else:
                time.sleep(0.02)
    finally:
        try:
            jlink.rtt_stop()
        except Exception:
            pass
        jlink.close()
        if out_fh:
            out_fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
