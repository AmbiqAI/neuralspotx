# usb_rpc

USB CDC RPC (Remote Procedure Call) example for Apollo510 EVB.

Implements a length-prefixed nanopb (Protocol Buffers) RPC transport over USB
CDC, allowing a host PC to invoke device-side functions. The device processes
incoming protobuf-encoded requests, dispatches them, and returns
protobuf-encoded responses.

## Features

- USB CDC bulk transport with framed messages (4-byte length prefix)
- nanopb serialization/deserialization (generated from `proto/nsx_rpc.proto`)
- Extensible dispatch table in `nsx_rpc_dispatch.c`
- Static allocation — no malloc

## Build

```bash
nsx configure --app-dir .
nsx build --app-dir .
nsx flash --app-dir .
```

## Host-side

See `tools/` for Python host-side RPC client utilities.

## Dependencies

- `nsx-usb` — USB CDC device driver
- `nsx-nanopb` — Protocol Buffers encoding
- `nsx-core` — System init and harness
