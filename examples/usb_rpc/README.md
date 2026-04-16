# usb_rpc

USB CDC RPC (Remote Procedure Call) example for Apollo510 EVB.

Implements a length-prefixed nanopb (Protocol Buffers) RPC transport over USB
CDC, allowing a host PC to invoke device-side functions. The device processes
incoming protobuf-encoded requests, dispatches them, and returns
protobuf-encoded responses.

## Features

- USB CDC bulk transport with framed messages (4-byte LE length prefix)
- nanopb serialization/deserialization (generated from `proto/nsx_rpc.proto`)
- Extensible dispatch table in `nsx_rpc_dispatch.c`
- Static allocation — no malloc

## RPC Messages

| Message | Direction | Description |
|---------|-----------|-------------|
| `PING` | req → resp | Round-trip latency test; response includes device uptime |
| `STATUS` | req → resp | Device identity: board name, firmware version |
| `INFER` | req → resp | Toy inference: sends raw bytes, device returns predicted class + confidence |

## Build & Flash

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .
```

## Host-Side Usage

A Python RPC client is included in `tools/`:

```bash
# Install dependencies (from neuralspotx root)
pip install pyserial grpcio-tools

# Run the demo (auto-detects the CDC port)
python tools/rpc_host.py
```

Or specify a port explicitly:

```bash
python tools/rpc_host.py /dev/cu.usbmodem1234
```

### Expected Output

```
Connecting to /dev/cu.usbmodem14301 ...
Connected.

=== PING ===
  seq=0  uptime=1234 ms  RTT=3.2 ms
  seq=1  uptime=1237 ms  RTT=2.8 ms
  seq=2  uptime=1240 ms  RTT=2.9 ms

=== STATUS ===
  board       : apollo510_evb
  fw_version  : 1.0.0
  free_heap   : 0 bytes

=== INFERENCE ===
  trial 0: class=2  label='run'    conf=0.617
  trial 1: class=4  label='unknown' conf=0.539
  trial 2: class=1  label='walk'   conf=0.680
  trial 3: class=0  label='idle'   conf=0.562
  trial 4: class=3  label='gesture' conf=0.711

Done.
```

> **Note:** The inference handler is a toy stub — it sums input bytes and maps
> to one of 5 classes.  Replace `handle_infer()` in `nsx_rpc_dispatch.c` with
> a real model for production use.

## Wire Protocol

```
┌──────────────┬─────────────────────────────────┐
│ 4 bytes (LE) │ nanopb-encoded NsxRpcMessage     │
│  payload len │                                   │
└──────────────┴─────────────────────────────────┘
```

Both host and device use the same framing.  The `.proto` definition is in
`proto/nsx_rpc.proto`; the Python bindings are auto-generated on first run.

## Project Layout

```
usb_rpc/
├── CMakeLists.txt
├── nsx.yml
├── proto/
│   ├── nsx_rpc.proto        Protocol definition
│   ├── nsx_rpc.options      nanopb options (field sizes)
│   ├── nsx_rpc.pb.c         Generated C bindings
│   └── nsx_rpc.pb.h
├── src/
│   ├── main.c               USB init + framing state machine
│   ├── nsx_rpc_dispatch.c   Handler stubs (ping, infer, status)
│   └── nsx_rpc_dispatch.h
└── tools/
    ├── rpc_host.py           Python host-side client
    └── nsx_rpc_pb2.py        Generated Python bindings
```

## Dependencies

- `nsx-usb` — USB CDC device driver
- `nsx-nanopb` — Protocol Buffers encoding
- `nsx-core` — System init and harness
