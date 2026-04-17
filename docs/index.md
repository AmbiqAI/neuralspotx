---
hide:
  - navigation
  - toc
---

<div class="landing" markdown>

<div class="hero" markdown>

![neuralspotx](./assets/neuralspotx-logo-light.png#only-light){ .hero-logo }
![neuralspotx](./assets/neuralspotx-logo-dark.png#only-dark){ .hero-logo }

# Bare-metal firmware development, simplified.

A CLI-first build workflow for Ambiq SoCs — scaffold, build, flash, and
stream live output in five commands.
{ .hero-sub }

[Get Started](getting-started/index.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/AmbiqAI/neuralspotx){ .md-button }

</div>

---

## How it Works

Five commands cover the full firmware lifecycle.
{ .section-sub }

![NSX workflow](./assets/workflow-light.svg#only-light){ .diagram }
![NSX workflow](./assets/workflow-dark.svg#only-dark){ .diagram }

```bash
nsx create-app my_app --board apollo510_evb
nsx configure  --app-dir my_app
nsx build      --app-dir my_app
nsx flash      --app-dir my_app   # J-Link / SWD
nsx view       --app-dir my_app   # live SWO stream
```

Every generated project is vanilla CMake — inspect, extend, or eject with no vendor lock-in.
{ .section-sub }

---

## Module Ecosystem

Declare dependencies in YAML. NSX resolves versioned modules and wires them into your build.
{ .section-sub }

![Module ecosystem](./assets/ecosystem-light.svg#only-light){ .diagram .diagram--narrow }
![Module ecosystem](./assets/ecosystem-dark.svg#only-dark){ .diagram .diagram--narrow }

Modules are plain Git repos with a `module.yaml` descriptor. Adding one is a pull request, not a toolchain project.
{ .section-sub }

---

## Features

<div class="grid cards" markdown>

-   :material-console: __CLI Lifecycle__

    ---

    `create-app` · `configure` · `build` · `flash` · `view` — the entire
    workflow from scaffolding to live SWO output.

-   :material-package-variant: __Declarative Modules__

    ---

    Declare dependencies in YAML. NSX fetches versioned board support, HALs,
    drivers, and libraries from the registry.

-   :material-chip: __Multi-Board Targets__

    ---

    Built-in definitions for Apollo3, Apollo4, and Apollo510 EVBs. One board
    per app, pin-level config included.

-   :material-cog: __Standard CMake__

    ---

    No proprietary build system. Generated projects are vanilla CMake —
    inspect, extend, or eject at any time.

-   :material-speedometer: __Performance Tooling__

    ---

    PMU profiling, Cortex-M cycle counters, and Joulescope power-measurement
    scripts built in.

-   :material-usb: __Ready-Made Examples__

    ---

    Eight maintained examples — hello world, CoreMark, PMU, power benchmarking,
    audio capture, USB serial, and USB RPC.

</div>

---

## Where to Start

<div class="grid cards" markdown>

-   :material-rocket-launch: __New to NSX?__

    ---

    Install the toolchain, create your first app, and build it in minutes.

    [Getting Started →](getting-started/index.md)

-   :material-book-open-variant: __Deep Dive__

    ---

    App model, module resolution, board definitions, and build workflows.

    [User Guide →](user-guide/app-model.md)

-   :material-console-line: __CLI Reference__

    ---

    Flags, options, and usage for every `nsx` subcommand.

    [Commands →](reference/cli-overview.md)

-   :material-flask-outline: __Browse Examples__

    ---

    CoreMark, PMU profiling, power benchmarking, USB serial, and more.

    [Examples →](examples/index.md)

</div>

</div>
