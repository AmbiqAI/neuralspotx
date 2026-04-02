#!/usr/bin/env python3
"""
rpc_host.py — Host-side client for the NSX USB RPC demo.

Usage:
    python3 rpc_host.py [PORT] [--webusb]

    PORT defaults to auto-detect (first /dev/cu.usbmodem* on macOS,
         or /dev/ttyACM0 on Linux).

Wire protocol (same as device side):
    [ uint32 LE length ] [ nanopb-encoded NsxRpcMessage ]

Requirements:
    pip install pyserial nanopb
    protoc and nanopb_generator must be in PATH (for regeneration only).

The .pb2.py used here is generated from proto/nsx_rpc.proto via:
    protoc --python_out=. --proto_path=../proto ../proto/nsx_rpc.proto
    (optional — this script regenerates on first run if needed)
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import struct
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Regenerate the Python protobuf bindings from the .proto if they're missing
# ---------------------------------------------------------------------------

PROTO_DIR = Path(__file__).parent.parent / "proto"
PB2_PATH  = Path(__file__).parent / "nsx_rpc_pb2.py"

def _ensure_pb2() -> None:
    """Generate nsx_rpc_pb2.py if missing or stale (import fails)."""
    if PB2_PATH.exists():
        # Validate that the existing file is importable — a stale file
        # generated against a different protobuf version will fail here.
        try:
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location("_pb2_probe", PB2_PATH)
            mod  = _ilu.module_from_spec(spec)   # type: ignore[arg-type]
            spec.loader.exec_module(mod)          # type: ignore[union-attr]
            return  # all good
        except Exception:
            print(f"Stale {PB2_PATH.name} detected — regenerating ...", flush=True)
            PB2_PATH.unlink(missing_ok=True)

    print(f"Generating {PB2_PATH.name} from proto ...", flush=True)
    import subprocess
    # grpcio-tools bundles its own protoc that always matches the installed
    # protobuf Python package — no system-protoc version mismatch possible.
    res = subprocess.run(
        [sys.executable, "-m", "grpc_tools.protoc",
         f"--proto_path={PROTO_DIR}",
         f"--python_out={PB2_PATH.parent}",
         str(PROTO_DIR / "nsx_rpc.proto")],
        capture_output=True, text=True
    )
    if res.returncode != 0:
        print("ERROR: could not generate nsx_rpc_pb2.py")
        print(res.stderr)
        print("Run: uv sync --group examples   (from the neuralspotx root)")
        sys.exit(1)
    if not PB2_PATH.exists():
        print("ERROR: grpc_tools.protoc ran but nsx_rpc_pb2.py was not created")
        sys.exit(1)

_ensure_pb2()

# Add tools dir so we can import the generated pb2
sys.path.insert(0, str(PB2_PATH.parent))
import nsx_rpc_pb2 as pb2  # type: ignore

# ---------------------------------------------------------------------------
# Serial transport
# ---------------------------------------------------------------------------

import serial
import serial.tools.list_ports

LOG = logging.getLogger(__name__)


def _find_port() -> str:
    """Auto-detect the first Ambiq USB CDC port."""
    candidates = serial.tools.list_ports.comports()
    for p in candidates:
        desc = (p.description or "").lower()
        mfr  = (p.manufacturer or "").lower()
        if "ambiq" in desc or "ambiq" in mfr or "nsx" in desc:
            return p.device
    # Fallback to first usbmodem / ttyACM
    for p in candidates:
        if "usbmodem" in p.device or "ttyACM" in p.device or "ttyUSB" in p.device:
            return p.device
    raise RuntimeError("No USB CDC port found. Pass PORT explicitly.")


class RpcTransport:
    """Framed serial transport: [ uint32 LE length ] [ payload ]."""

    HDR_SIZE = 4

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 5.0) -> None:
        self._ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        self._ser.dtr = True   # Required: device checks DTR for CDC connected
        time.sleep(0.3)        # Let DTR propagate

    def close(self) -> None:
        self._ser.close()

    def send(self, payload: bytes) -> None:
        hdr = struct.pack("<I", len(payload))
        self._ser.write(hdr + payload)
        self._ser.flush()

    def recv(self) -> bytes:
        hdr = self._ser.read(self.HDR_SIZE)
        if len(hdr) < self.HDR_SIZE:
            raise TimeoutError("Timeout waiting for response header")
        (length,) = struct.unpack("<I", hdr)
        if length == 0 or length > 1024:
            raise ValueError(f"Implausible frame length {length}")
        payload = self._ser.read(length)
        if len(payload) < length:
            raise TimeoutError(f"Timeout: expected {length} bytes, got {len(payload)}")
        return bytes(payload)

    def call(self, msg: pb2.NsxRpcMessage) -> pb2.NsxRpcMessage:  # type: ignore
        self.send(msg.SerializeToString())
        raw = self.recv()
        resp = pb2.NsxRpcMessage()
        resp.ParseFromString(raw)
        return resp


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def ping(t: RpcTransport, seq: int = 0) -> pb2.NsxRpcMessage:  # type: ignore
    req = pb2.NsxRpcMessage(
        type=pb2.NSX_MSG_PING_REQ,
        ping_req=pb2.NsxPingRequest(seq=seq),
    )
    return t.call(req)


def infer(t: RpcTransport, model_id: int, data: bytes) -> pb2.NsxRpcMessage:  # type: ignore
    req = pb2.NsxRpcMessage(
        type=pb2.NSX_MSG_INFER_REQ,
        infer_req=pb2.NsxInferRequest(model_id=model_id, input=data),
    )
    return t.call(req)


def status(t: RpcTransport) -> pb2.NsxRpcMessage:  # type: ignore
    req = pb2.NsxRpcMessage(
        type=pb2.NSX_MSG_STATUS_REQ,
        status_req=pb2.NsxStatusRequest(reserved=0),
    )
    return t.call(req)


# ---------------------------------------------------------------------------
# Demo main
# ---------------------------------------------------------------------------

def demo(port: str) -> None:
    print(f"Connecting to {port} ...", flush=True)
    t = RpcTransport(port)
    print("Connected.\n")

    # --- Ping ---
    print("=== PING ===")
    for i in range(3):
        t0 = time.monotonic()
        r = ping(t, seq=i)
        rtt_ms = (time.monotonic() - t0) * 1000
        print(f"  seq={r.ping_resp.seq}  uptime={r.ping_resp.uptime_ms} ms  "
              f"RTT={rtt_ms:.1f} ms")

    print()

    # --- Status ---
    print("=== STATUS ===")
    r = status(t)
    s = r.status_resp
    ver = s.firmware_version
    print(f"  board       : {s.board_name.decode()}")
    print(f"  fw_version  : {(ver>>16)&0xFF}.{(ver>>8)&0xFF}.{ver&0xFF}")
    print(f"  free_heap   : {s.free_heap_bytes} bytes")
    print()

    # --- Inference ---
    print("=== INFERENCE ===")
    import random
    for trial in range(5):
        payload = bytes([random.randint(0, 255) for _ in range(32)])
        r = infer(t, model_id=0, data=payload)
        ir = r.infer_resp
        print(f"  trial {trial}: class={ir.class_id}  "
              f"label={ir.label.decode()!r}  conf={ir.confidence:.3f}")

    print()
    t.close()
    print("Done.")


def main() -> None:
    ap = argparse.ArgumentParser(description="NSX USB RPC host demo")
    ap.add_argument("port", nargs="?", help="Serial port (auto-detect if omitted)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    port = args.port or _find_port()
    demo(port)


if __name__ == "__main__":
    main()
