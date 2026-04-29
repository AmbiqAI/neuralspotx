# Examples

Eight ready-to-build example apps live in the
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples)
directory of the `neuralspotx` repo. Each one is a self-contained NSX
app — the same shape that `nsx create-app` produces — with its own
`nsx.yml` manifest and `nsx.lock` receipt.

All examples target the **Apollo510 EVB** (`apollo510_evb` profile).

## Quick Start

The recommended flow is to install `nsx` once and create your own app
(see [Getting Started](../getting-started/first-app.md)). To try a
maintained example, grab the folder out of the repo — there is no
workspace or full clone required:

```bash
curl -L https://github.com/AmbiqAI/neuralspotx/archive/refs/heads/main.tar.gz \
  | tar -xz -f - --strip-components=2 neuralspotx-main/examples/hello_world
cd hello_world

nsx configure
nsx build
nsx flash    # requires J-Link
nsx view     # live SWO stream
```

(Contributors who already have the repo cloned can simply `cd
neuralspotx/examples/hello_world` and run the same commands.)

## Available Examples

<div class="card-grid card-grid--2" markdown>
<div class="card" markdown>
### :material-hand-wave: [hello_world](hello_world.md)
Minimal SWO printf loop. Start here to verify your toolchain and board.
</div>
<div class="card" markdown>
### :material-speedometer: [coremark](coremark.md)
EEMBC CoreMark with ITCM execution and NVM shutdown for clean power numbers.
</div>
<div class="card" markdown>
### :material-lightning-bolt: [power_benchmark](power_benchmark.md)
Three-phase power measurement: CoreMark, idle, and deep sleep.
</div>
<div class="card" markdown>
### :material-counter: [pmu_profiling](pmu_profiling.md)
Cortex-M55 PMU cycle counting, cache hits, and branch mispredicts.
</div>
<div class="card" markdown>
### :material-brain: [kws_infer](kws_infer.md)
TFLite Micro keyword-spotting inference with CMSIS-NN kernels.
</div>
<div class="card" markdown>
### :material-microphone: [audio_capture](audio_capture.md)
PDM microphone capture with RMS/peak statistics over SWO.
</div>
<div class="card" markdown>
### :material-usb: [usb_serial](usb_serial.md)
USB CDC virtual COM port echo app.
</div>
<div class="card" markdown>
### :material-swap-horizontal: [usb_rpc](usb_rpc.md)
USB vendor-class RPC with nanopb protobuf serialization.
</div>
</div>
