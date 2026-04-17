# Getting Started

Go from a fresh machine to a running firmware image in minutes. The three
guides below cover everything you need — prerequisites, your first build,
and a library of ready-made examples to explore.

<div class="card-grid card-grid--3" markdown>
<div class="card" markdown>
### :material-download: Install and Setup
Install the toolchain, set up the Python environment, and verify
everything works with `nsx doctor`.

[Install &rarr;](install.md)
</div>
<div class="card" markdown>
### :material-hammer-wrench: First App
Scaffold a project, resolve modules, build the firmware, flash it to an
EVB, and stream live SWO output.

[Build your first app &rarr;](first-app.md)
</div>
<div class="card" markdown>
### :material-folder-open: Examples
Eight maintained example apps — hello world, CoreMark, PMU profiling,
power benchmarking, audio capture, USB serial, and more.

[Browse examples &rarr;](examples.md)
</div>
</div>

## What You'll Need

| Requirement | Why |
|---|---|
| **Python 3.10+** | NSX CLI and module resolution run on Python |
| **uv** | Fast dependency manager used by the project |
| **CMake + Ninja** | Build system underneath every generated app |
| **Arm GNU Toolchain** | Cross-compiler for Cortex-M targets |
| **SEGGER J-Link** | Flash and SWO viewer (`nsx flash` / `nsx view`) |

All of these are covered in detail on the [Install and Setup](install.md) page.

## Notation

Throughout the docs you'll see two placeholder paths:

- `<nsx-repo>` — the root of your `neuralspotx` clone
- `<app-dir>` — the directory of a generated or example app

Replace them with your actual paths when running commands.
