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
maintained example without a git clone or a separate workspace, use the
snippet below. (Note: this still downloads the full repository tarball;
`tar` then extracts only the example folder you ask for.)

```bash
curl -fL https://github.com/AmbiqAI/neuralspotx/archive/refs/heads/main.tar.gz \
  | tar -xz -f - --strip-components=2 neuralspotx-main/examples/hello_world
cd hello_world

nsx configure
nsx build
nsx flash   # requires J-Link
nsx view    # live SWO stream
```

Contributors who already have the repo cloned can simply
`cd neuralspotx/examples/hello_world` and run the same commands.

Because those commands run from the app root, NSX resolves the app directory
from the nearest `nsx.yml` automatically.

## Available Examples

<div class="grid cards" markdown>

-   :material-hand-wave:{ .lg .middle } __[hello_world](hello_world.md)__

    ---

    Minimal SWO printf loop. Start here to verify your toolchain and board.

-   :material-speedometer:{ .lg .middle } __[coremark](coremark.md)__

    ---

    EEMBC CoreMark with ITCM execution and NVM shutdown for clean power numbers.

-   :material-lightning-bolt:{ .lg .middle } __[power_benchmark](power_benchmark.md)__

    ---

    Three-phase power measurement: CoreMark, idle, and deep sleep.

-   :material-counter:{ .lg .middle } __[pmu_profiling](pmu_profiling.md)__

    ---

    Cortex-M55 PMU cycle counting, cache hits, and branch mispredicts.

-   :material-brain:{ .lg .middle } __[kws_infer](kws_infer.md)__

    ---

    TFLite Micro keyword-spotting inference with CMSIS-NN kernels.

-   :material-microphone:{ .lg .middle } __[audio_capture](audio_capture.md)__

    ---

    PDM microphone capture with RMS/peak statistics over SWO.

-   :material-usb:{ .lg .middle } __[usb_serial](usb_serial.md)__

    ---

    USB CDC virtual COM port echo app.

-   :material-swap-horizontal:{ .lg .middle } __[usb_rpc](usb_rpc.md)__

    ---

    USB vendor-class RPC with nanopb protobuf serialization.

</div>
