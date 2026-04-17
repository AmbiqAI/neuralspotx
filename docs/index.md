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

## Quick Links

<div class="quick-links" markdown>

[Features](#features-at-a-glance){ .md-button }
[What is NSX?](#what-is-nsx){ .md-button }
[How it Works](#how-it-works){ .md-button }
[Module Catalog](user-guide/module-catalog.md){ .md-button }
[Create First App](getting-started/first-app.md){ .md-button }
[Examples](examples/index.md){ .md-button }

</div>

---

## Features at a Glance

<div class="grid cards feature-cards" markdown>

-   :material-console: __5-command lifecycle__

    ---

    Create, configure, build, flash, and live-view from one CLI.

-   :material-package-variant: __Registry-backed modules__

    ---

    Declarative dependencies with versioned module resolution.

-   :material-chip: __Board-ready targets__

    ---

    Built-in Apollo3, Apollo4, Apollo5, and Apollo510 board coverage.

-   :material-cog: __Standard CMake output__

    ---

    Generated projects stay transparent and fully editable.

-   :material-speedometer: __Perf and power tooling__

    ---

    PMU profiling, cycle counters, and Joulescope workflows included.

-   :material-usb: __Maintained example apps__

    ---

    Ready-to-run examples for USB, audio, CoreMark, and more.

</div>

---

## What is NSX?

NSX is a CLI-first firmware workflow for Ambiq SoCs that keeps app projects
simple, reproducible, and easy to inspect.
{ .section-sub }

It focuses on source-controlled configuration, reusable modules, and generated
vanilla CMake projects so teams can move quickly without hidden build tooling.
{ .section-sub }

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
