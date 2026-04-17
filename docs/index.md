---
hide:
  - navigation
  - toc
---

<div class="hero-logo" markdown>
[![neuralspotx](./assets/neuralspotx-logo-light.png#only-light)](https://github.com/AmbiqAI/neuralspotx)
[![neuralspotx](./assets/neuralspotx-logo-dark.png#only-dark)](https://github.com/AmbiqAI/neuralspotx)
</div>

# NSX

**Task-focused bare-metal application workflow for Ambiq SoCs and boards.**

NSX is designed for board bring-up, smoke-test applications,
profiling and instrumentation workflows, and targeted feature validation
such as USB or interface demos.

## How it Works

<div class="workflow-pipeline">
  <img src="./assets/workflow-light.svg#only-light" alt="NSX workflow: create-app → configure → build → flash → view">
  <img src="./assets/workflow-dark.svg#only-dark" alt="NSX workflow: create-app → configure → build → flash → view">
</div>

Generated apps stay explicit and inspectable — one board, one SoC, one
toolchain, ordinary CMake structure.

## Features

<div class="feature-grid" markdown>
<div class="card" markdown>
### :material-console: CLI Workflow
`create-app` · `configure` · `build` · `flash` · `view` — the full app lifecycle from a single tool.
</div>
<div class="card" markdown>
### :material-package-variant: Module Registry
Declarative module resolution — pull board support, HALs, peripherals, and libraries from versioned repos.
</div>
<div class="card" markdown>
### :material-chip: Board Definitions
Built-in definitions for Apollo4, Apollo510, and more. One board per app, zero ambiguity.
</div>
<div class="card" markdown>
### :material-cog: CMake Native
Standard CMake under the hood. Inspect, extend, or eject at any time.
</div>
</div>

## Where to Start

<div class="feature-grid" markdown>
<div class="card" markdown>
### :material-rocket-launch: New to NSX?
Start with **[Getting Started](getting-started/index.md)** — install prerequisites, create your first app, and build it.
</div>
<div class="card" markdown>
### :material-book-open-variant: Already using it?
The **[User Guide](user-guide/app-model.md)** covers the app model, modules, boards, and build workflows in depth.
</div>
<div class="card" markdown>
### :material-console-line: Need a CLI reference?
The **[Command Reference](reference/cli-overview.md)** has exact flags and syntax for every `nsx` subcommand.
</div>
<div class="card" markdown>
### :material-flask-outline: Want working code?
Browse the **[Examples](examples/hello_world.md)** — hello world, CoreMark, PMU profiling, USB, and more.
</div>
</div>
