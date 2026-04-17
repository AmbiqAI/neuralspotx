# Examples

Eight ready-to-build example apps ship in the
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples)
directory. Each one is a self-contained NSX app — clone the repo and you
can configure, build, and flash immediately.

## Quick Start

Pick any example, configure, build, and (optionally) flash:

```bash
git clone https://github.com/AmbiqAI/neuralspotx.git
cd neuralspotx/examples/hello_world

nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .   # requires an EVB connected via J-Link
nsx view      --app-dir .   # streams SWO output in the terminal
```

`nsx configure` automatically fetches any missing registry modules — there
is no separate install step.

## Available Examples

All examples target the **Apollo510 EVB** (`apollo510_evb` profile).

### :material-hand-wave: hello_world

Minimal app — a SWO printf loop and nothing else. Start here to verify
that your toolchain, board connection, and SWO viewer all work.

**Extra modules:** *(base profile only)*

### :material-speedometer: coremark

Industry-standard [EEMBC CoreMark](https://www.eembc.org/coremark/)
benchmark with ITCM execution and NVM shutdown for clean power numbers.
Includes a Joulescope capture script for automated power measurement.

**Extra modules:** `nsx-power`

### :material-lightning-bolt: power_benchmark

Three-phase power measurement app: CoreMark under load, `while(1)` idle,
and deep-sleep shutdown. Designed to pair with a Joulescope JS220 for
characterizing board-level power consumption.

**Extra modules:** `nsx-power`

### :material-counter: pmu_profiling

Cortex-M55 Performance Monitoring Unit (PMU) demonstration. Counts CPU
cycles, cache hits, and branch mispredicts around a code region, then
prints the results over SWO.

**Extra modules:** `nsx-pmu-armv8m`

### :material-brain: kws_infer

Keyword-spotting inference using TensorFlow Lite for Microcontrollers and
CMSIS-NN optimized kernels. Runs a small neural network on a canned audio
buffer and reports the classification result.

**Extra modules:** `cmsis-nn`

### :material-microphone: audio_capture

PDM microphone capture on the Apollo510 EVB. Streams audio statistics
(RMS, peak) over SWO — useful for verifying microphone wiring and clock
configuration.

**Extra modules:** `nsx-audio`

### :material-usb: usb_serial

USB CDC (virtual COM port) echo app. Enumerates as a USB serial device
and echoes back anything sent from the host.

**Extra modules:** `nsx-usb`

### :material-swap-horizontal: usb_rpc

USB vendor-class RPC endpoint with protobuf serialization. Demonstrates
bidirectional host-to-device communication using nanopb-encoded messages
over a USB bulk interface.

**Extra modules:** `nsx-usb`, `nsx-nanopb`

## Switching Between Examples

Every example follows the same workflow — just change directories:

```bash
cd ../pmu_profiling
nsx configure --app-dir .
nsx build     --app-dir .
```

## Example Directory Layout

Each example follows a consistent structure:

```text
<example>/
├── nsx.yml          # module manifest and board target
├── CMakeLists.txt   # CMake entry point
├── src/
│   └── main.c       # application source
└── README.md        # build and usage instructions
```

The `modules/` and `build/` directories are gitignored and regenerated
by `nsx configure` — you'll never need to check them in.
