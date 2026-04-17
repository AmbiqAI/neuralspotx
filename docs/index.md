---
hide:
  - navigation
  - toc
---

<div class="landing" markdown>

<div class="hero-logo" markdown>
[![neuralspotx](./assets/neuralspotx-logo-light.png#only-light)](https://github.com/AmbiqAI/neuralspotx)
[![neuralspotx](./assets/neuralspotx-logo-dark.png#only-dark)](https://github.com/AmbiqAI/neuralspotx)
</div>

<p class="hero-tagline">Bare-metal firmware development, simplified.</p>

<p class="hero-sub">
NSX is a CLI-first build workflow for Ambiq SoCs. Scaffold a project,
declare module dependencies, compile with CMake, flash over J-Link, and
stream live SWO output — five commands from zero to running firmware.
</p>

<div class="hero-actions" markdown>

[Get Started](getting-started/index.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/AmbiqAI/neuralspotx){ .md-button }

</div>

---

## How it Works

<p class="section-sub">
Five commands cover the full firmware lifecycle — from an empty directory to
live output on hardware.
</p>

<div class="workflow-pipeline">
  <img src="./assets/workflow-light.svg#only-light" alt="NSX workflow: create-app → configure → build → flash → view">
  <img src="./assets/workflow-dark.svg#only-dark" alt="NSX workflow: create-app → configure → build → flash → view">
</div>

<div class="landing-code" markdown>

```bash
nsx create-app my_app --board apollo510_evb
nsx configure  --app-dir my_app
nsx build      --app-dir my_app
nsx flash      --app-dir my_app   # J-Link / SWD
nsx view       --app-dir my_app   # live SWO stream
```

</div>

Every generated project is ordinary CMake — inspect it, extend it, or hand
it to CI with no NSX dependency. No hidden build magic, no vendor lock-in.

---

## Module Ecosystem

<p class="section-sub">
Declare what your app needs in a YAML manifest. NSX resolves versioned
modules from a central registry and wires them into your build automatically.
</p>

<div class="ecosystem-diagram">
  <img src="./assets/ecosystem-light.svg#only-light" alt="Module ecosystem: SDK providers, BSPs, HALs, peripherals, and libraries compose into your app">
  <img src="./assets/ecosystem-dark.svg#only-dark" alt="Module ecosystem: SDK providers, BSPs, HALs, peripherals, and libraries compose into your app">
</div>

Modules are plain Git repos with a `module.yaml` descriptor — SDK providers,
board support packages, HAL layers, peripheral drivers, and utility libraries.
Adding a new module is a pull request, not a toolchain integration project.

---

## Features

<p class="section-sub">
Everything you need for board bring-up, benchmarking, and peripheral
validation — nothing you don't.
</p>

<div class="card-grid card-grid--3" markdown>
<div class="card" markdown>
### :material-console: CLI Lifecycle
`create-app` · `configure` · `build` · `flash` · `view` — the entire
firmware workflow from scaffolding to live SWO output.
</div>
<div class="card" markdown>
### :material-package-variant: Declarative Modules
Declare dependencies in YAML. NSX fetches versioned board support, HALs,
peripheral drivers, and libraries from the registry.
</div>
<div class="card" markdown>
### :material-chip: Multi-Board Targets
Built-in definitions for Apollo3, Apollo4, and Apollo510 EVBs. One board
per app, zero ambiguity, pin-level config included.
</div>
<div class="card" markdown>
### :material-cog: Standard CMake
No proprietary build system. Generated projects are vanilla CMake —
inspect, extend, or eject at any time.
</div>
<div class="card" markdown>
### :material-speedometer: Performance Tooling
PMU profiling, Cortex-M cycle counters, and Joulescope power-measurement
scripts. Characterize performance without external frameworks.
</div>
<div class="card" markdown>
### :material-usb: Ready-Made Examples
Eight maintained examples — hello world, CoreMark, PMU, power benchmarking,
audio capture, USB serial, and USB RPC.
</div>
</div>

---

## Where to Start

<div class="card-grid card-grid--2" markdown>
<div class="card" markdown>
### :material-rocket-launch: New to NSX?
Install the toolchain, create your first app, and build it in minutes.
**[Getting Started →](getting-started/index.md)**
</div>
<div class="card" markdown>
### :material-book-open-variant: Deep Dive
App model, module resolution, board definitions, and build workflows.
**[User Guide →](user-guide/app-model.md)**
</div>
<div class="card" markdown>
### :material-console-line: CLI Reference
Flags, options, and usage for every `nsx` subcommand.
**[Commands →](reference/cli-overview.md)**
</div>
<div class="card" markdown>
### :material-flask-outline: Browse Examples
CoreMark, PMU profiling, power benchmarking, USB serial, and more.
**[Examples →](examples/index.md)**
</div>
</div>

</div>
