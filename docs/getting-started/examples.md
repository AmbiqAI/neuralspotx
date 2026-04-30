# Examples

Eight ready-to-build example apps live in the
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples)
directory of the `neuralspotx` repo. Each one is a self-contained NSX
app — the same shape that `nsx create-app` produces — with its own
`nsx.yml` manifest and `nsx.lock` receipt.

## Quick Start

The normal app-developer flow is to install `nsx` once with `pipx` (see
[Install and Setup](install.md)) and create your own app:

```bash
nsx create-app my_app
cd my_app
nsx configure
nsx build
```

To try a maintained example without a git clone or a separate workspace,
use the snippet below. (Note: this still downloads the full repository
tarball; `tar` then extracts only the example folder you ask for.)

```bash
# One-shot: download the hello_world example and treat it like any app
curl -L https://github.com/AmbiqAI/neuralspotx/archive/refs/heads/main.tar.gz \
  | tar -xz -f - --strip-components=2 neuralspotx-main/examples/hello_world
cd hello_world

nsx configure
nsx build
nsx flash    # requires an EVB connected via J-Link
nsx view     # streams SWO output in the terminal
```

If you already have the repo cloned for contributing,
`cd neuralspotx/examples/hello_world` works the same way.

`nsx configure` automatically fetches any missing registry modules —
there is no separate install step.

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
