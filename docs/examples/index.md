# Examples

Eight ready-to-build example apps ship in the
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples)
directory. Each one is a self-contained NSX app — clone the repo and you
can configure, build, and flash immediately.

All examples target the **Apollo510 EVB** (`apollo510_evb` profile).

## Quick Start

```bash
git clone https://github.com/AmbiqAI/neuralspotx.git
cd neuralspotx/examples/hello_world

nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .   # requires J-Link
nsx view      --app-dir .   # live SWO stream
```

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
