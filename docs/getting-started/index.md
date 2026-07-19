# Getting Started

Go from a fresh machine to a running firmware image in minutes. The three
guides below cover everything you need — prerequisites, your first build,
and a library of ready-made examples to explore.

!!! info "What NSX is for"
    NSX is a development and evaluation vehicle for Ambiq SoCs — ideal for
    AI/ML bring-up, profiling, benchmarking, and demos. Prototype and
    measure here, then graduate proven work into your own build.

## What You'll Build

In about five minutes you'll scaffold an app, cross-compile it for an
**Apollo510 EVB**, flash it over J-Link, and watch a live SWO heartbeat
stream from the board — all driven by five `nsx` commands.

No board on hand? You can still install the toolchain and `configure` +
`build` a firmware image. Only `flash` and `view` need hardware.

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } __Install and Setup__

    ---

    Install the toolchain, set up the Python environment, and verify
    everything works with `nsx doctor`.

    [:octicons-arrow-right-24: Install](install/index.md)

-   :material-hammer-wrench:{ .lg .middle } __First App__

    ---

    Scaffold a project, resolve modules, build the firmware, flash it to an
    EVB, and stream live SWO output.

    [:octicons-arrow-right-24: Build your first app](first-app.md)

-   :material-folder-open:{ .lg .middle } __Examples__

    ---

    Ten maintained example apps — hello world, FreeRTOS, CoreMark, BLE,
    audio, USB, ML inference, profiling, and power measurement.

    [:octicons-arrow-right-24: Browse examples](../examples/)

</div>

## What You'll Need

A quick glance — see [Install and Setup](install/index.md) for versions and
platform-specific install commands.

| Requirement | Why |
|---|---|
| **Python 3.10+** | NSX CLI and module resolution run on Python |
| **uv** | Fast dependency manager used by the project |
| **CMake + Ninja** | Build system underneath every generated app |
| **Arm GNU Toolchain** | Default cross-compiler for Cortex-M targets |
| **SEGGER J-Link** | Flash and SWO viewer — only needed for `nsx flash` / `nsx view` |

armclang and ATfE are also supported, but optional — GCC builds every
example.

## Notation

Throughout the docs you'll see one universal placeholder path:

- `<app-dir>` — the directory of a generated or example app (whatever
  you passed to `nsx create-app`, or the path to a checked-out example).

Replace it with your actual path when running commands.
Contributor-oriented docs may also reference `<nsx-repo>`, the root of
a local clone of the `neuralspotx` repository — normal app developers
do not need one.
