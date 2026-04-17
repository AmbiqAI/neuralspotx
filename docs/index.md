---
hide:
  - navigation
  - toc
---

<div class="hero-logo" markdown>
[![neuralspotx](./assets/neuralspotx-logo-light.png#only-light)](https://github.com/AmbiqAI/neuralspotx)
[![neuralspotx](./assets/neuralspotx-logo-dark.png#only-dark)](https://github.com/AmbiqAI/neuralspotx)
</div>

<p class="hero-tagline">Bare-metal development, simplified.</p>

<p class="hero-description">
NSX is a task-focused CLI workflow for Ambiq SoCs and evaluation boards.
Scaffold a project, resolve hardware modules, build with CMake, flash over
J-Link, and stream SWO output — all from a single tool. Designed for board
bring-up, smoke tests, USB and interface demos, power profiling, and feature
validation.
</p>

<div class="hero-actions" markdown>

[Get Started](getting-started/index.md){ .md-button .md-button--primary }
[Browse Examples](examples/hello_world.md){ .md-button }

</div>

---

## How it Works

Five commands take you from an empty directory to running firmware.

<div class="workflow-pipeline">
  <img src="./assets/workflow-light.svg#only-light" alt="NSX workflow: create-app → configure → build → flash → view">
  <img src="./assets/workflow-dark.svg#only-dark" alt="NSX workflow: create-app → configure → build → flash → view">
</div>

Every generated app is explicit and inspectable — one board, one SoC, one
toolchain, ordinary CMake. No hidden build magic, no vendor lock-in.
Inspect the generated `CMakeLists.txt`, extend it, or eject at any time.

---

## Module Ecosystem

You declare what your app needs in a YAML manifest; NSX resolves versioned
board-support packages, HALs, peripheral drivers, and libraries from a
central registry — then wires them into your CMake build automatically.

<div class="ecosystem-diagram">
  <img src="./assets/ecosystem-light.svg#only-light" alt="NSX module ecosystem: SDK, BSP, HAL, Peripherals, Libraries, and Core modules compose into your app">
  <img src="./assets/ecosystem-dark.svg#only-dark" alt="NSX module ecosystem: SDK, BSP, HAL, Peripherals, Libraries, and Core modules compose into your app">
</div>

Modules are plain Git repos with a `module.yaml` descriptor. Adding
a new peripheral driver or library is a pull request — no special
toolchain integration needed.

---

## Features

<div class="feature-grid" markdown>
<div class="card" markdown>
### :material-console: Full CLI Lifecycle
`create-app` · `configure` · `build` · `flash` · `view` — five subcommands cover the entire firmware workflow from scaffolding to live SWO output.
</div>
<div class="card" markdown>
### :material-package-variant: Declarative Modules
Declare dependencies in YAML — NSX fetches versioned board support, HALs, peripheral drivers, and libraries from the registry automatically.
</div>
<div class="card" markdown>
### :material-chip: Multi-Board Support
Built-in definitions for Apollo3, Apollo4, Apollo510, and their EVBs. One board per app, zero target ambiguity, pin-level configuration included.
</div>
<div class="card" markdown>
### :material-cog: Standard CMake
No custom build system. NSX generates ordinary CMake projects you can inspect, extend, or hand off to CI without any NSX dependency.
</div>
<div class="card" markdown>
### :material-speedometer: Performance Tooling
Built-in PMU profiling, Cortex-M cycle counters, and power-measurement scripting. Measure what matters without bolting on external frameworks.
</div>
<div class="card" markdown>
### :material-usb: Peripheral Examples
Ready-to-flash examples for USB CDC/vendor, UART, I2C, SPI, audio capture, and keyword-spotting inference — each with a tested README.
</div>
</div>

---

## Where to Start

<div class="feature-grid start-grid" markdown>
<div class="card" markdown>
### :material-rocket-launch: New to NSX?
Start with **[Getting Started](getting-started/index.md)** — install the prerequisites, create your first app, and build it in minutes.
</div>
<div class="card" markdown>
### :material-book-open-variant: Already using it?
The **[User Guide](user-guide/app-model.md)** covers the app model, module resolution, board definitions, and build workflows in depth.
</div>
<div class="card" markdown>
### :material-console-line: CLI Reference
The **[Command Reference](reference/cli-overview.md)** has exact flags, options, and usage examples for every `nsx` subcommand.
</div>
<div class="card" markdown>
### :material-flask-outline: Working Code
Browse the **[Examples](examples/hello_world.md)** — hello world, CoreMark, PMU profiling, power benchmarking, USB serial, and more.
</div>
</div>
