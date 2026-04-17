---
hide:
  - navigation
  - toc
---

<section class="lp-hero">
  <div class="lp-hero__inner">
    <div class="hero-logo" markdown>
[![neuralspotx](./assets/neuralspotx-logo-light.png#only-light)](https://github.com/AmbiqAI/neuralspotx)
[![neuralspotx](./assets/neuralspotx-logo-dark.png#only-dark)](https://github.com/AmbiqAI/neuralspotx)
    </div>
    <p class="lp-hero__tagline">Bare-metal firmware development, simplified.</p>
    <p class="lp-hero__sub">
      A CLI-first build workflow for Ambiq SoCs — scaffold, build, flash, and
      stream live output in five commands.
    </p>
    <div class="lp-hero__actions" markdown>

[Get Started](getting-started/index.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/AmbiqAI/neuralspotx){ .md-button }

</div>
  </div>
</section>

<section class="lp-section">
  <div class="lp-section__inner">
    <h2 class="lp-section__title">How it Works</h2>
    <p class="lp-section__sub">Five commands cover the full firmware lifecycle.</p>
    <div class="lp-workflow">
      <img src="./assets/workflow-light.svg#only-light" alt="NSX workflow">
      <img src="./assets/workflow-dark.svg#only-dark" alt="NSX workflow">
    </div>
    <div class="lp-code" markdown>

```bash
nsx create-app my_app --board apollo510_evb
nsx configure  --app-dir my_app
nsx build      --app-dir my_app
nsx flash      --app-dir my_app   # J-Link / SWD
nsx view       --app-dir my_app   # live SWO stream
```

</div>
    <p class="lp-section__foot">Every generated project is vanilla CMake — inspect, extend, or eject with no vendor lock-in.</p>
  </div>
</section>

<section class="lp-section lp-section--alt">
  <div class="lp-section__inner">
    <h2 class="lp-section__title">Module Ecosystem</h2>
    <p class="lp-section__sub">Declare dependencies in YAML. NSX resolves versioned modules and wires them into your build.</p>
    <div class="lp-ecosystem">
      <img src="./assets/ecosystem-light.svg#only-light" alt="Module ecosystem">
      <img src="./assets/ecosystem-dark.svg#only-dark" alt="Module ecosystem">
    </div>
    <p class="lp-section__foot">Modules are plain Git repos with a <code>module.yaml</code> descriptor. Adding one is a pull request, not a toolchain project.</p>
  </div>
</section>

<section class="lp-section">
  <div class="lp-section__inner">
    <h2 class="lp-section__title">Features</h2>
    <div class="lp-grid lp-grid--3" markdown>
<div class="lp-card" markdown>
### :material-console: CLI Lifecycle
`create-app` · `configure` · `build` · `flash` · `view` — the entire workflow from scaffolding to live SWO output.
</div>
<div class="lp-card" markdown>
### :material-package-variant: Declarative Modules
Declare dependencies in YAML. NSX fetches versioned board support, HALs, drivers, and libraries from the registry.
</div>
<div class="lp-card" markdown>
### :material-chip: Multi-Board Targets
Built-in definitions for Apollo3, Apollo4, and Apollo510 EVBs. One board per app, pin-level config included.
</div>
<div class="lp-card" markdown>
### :material-cog: Standard CMake
No proprietary build system. Generated projects are vanilla CMake — inspect, extend, or eject at any time.
</div>
<div class="lp-card" markdown>
### :material-speedometer: Performance Tooling
PMU profiling, Cortex-M cycle counters, and Joulescope power-measurement scripts built in.
</div>
<div class="lp-card" markdown>
### :material-usb: Ready-Made Examples
Eight maintained examples — hello world, CoreMark, PMU, power benchmarking, audio capture, USB serial, and USB RPC.
</div>
    </div>
  </div>
</section>

<section class="lp-section lp-section--alt">
  <div class="lp-section__inner">
    <h2 class="lp-section__title">Where to Start</h2>
    <div class="lp-grid lp-grid--2" markdown>
<div class="lp-card" markdown>
### :material-rocket-launch: New to NSX?
Install the toolchain, create your first app, and build it in minutes.
**[Getting Started →](getting-started/index.md)**
</div>
<div class="lp-card" markdown>
### :material-book-open-variant: Deep Dive
App model, module resolution, board definitions, and build workflows.
**[User Guide →](user-guide/app-model.md)**
</div>
<div class="lp-card" markdown>
### :material-console-line: CLI Reference
Flags, options, and usage for every `nsx` subcommand.
**[Commands →](reference/cli-overview.md)**
</div>
<div class="lp-card" markdown>
### :material-flask-outline: Browse Examples
CoreMark, PMU profiling, power benchmarking, USB serial, and more.
**[Examples →](examples/index.md)**
</div>
    </div>
  </div>
</section>
