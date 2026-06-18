---
hide:
  - toc
---

<div class="landing" markdown>

<section class="l-hero" markdown>

<p class="l-eyebrow">AI on Ambiq</p>

# neuralSPOT-X

<p class="l-lead">The single CLI, <strong>NSX</strong> for short, that scaffolds, builds,
flashes, and profiles firmware for Ambiq SoCs, with first-class paths into the
Helia runtime, ahead-of-time, and profiling stack.</p>

<div class="l-hero__cta" markdown>
[Get started](getting-started/index.md){ .md-button .md-button--primary }
[Build your first app](getting-started/first-app.md){ .md-button }
</div>

<div class="l-terminal" markdown>

```bash
nsx create-app my_app --board apollo510_evb
cd my_app
nsx configure
nsx build
nsx flash
nsx view
```

</div>

</section>

<section class="l-section" markdown>

<div class="l-section__head" markdown>
<p class="l-eyebrow">Workflow</p>
## Five commands, idea to silicon
<p class="l-lead">Every NSX app follows the same lifecycle. Each step is a single command
against a transparent CMake + Ninja project you can always inspect.</p>
</div>

<div class="l-grid l-grid--4 l-steps" markdown>

<div class="l-card l-step" markdown>
#### `create-app`
Scaffold an app project targeting a real Ambiq board.
</div>

<div class="l-card l-step" markdown>
#### `configure`
Resolve YAML module dependencies and lock versions.
</div>

<div class="l-card l-step" markdown>
#### `build`
Compile with CMake and Ninja into a flashable image.
</div>

<div class="l-card l-step" markdown>
#### `flash`
Program the connected board and start the firmware.
</div>

<div class="l-card l-step" markdown>
#### `view`
Stream live SWO output and inspect on-device results.
</div>

</div>

</section>

<section class="l-section" markdown>

<div class="l-section__head" markdown>
<p class="l-eyebrow">Helia stack</p>
## A direct path to AI on device
<p class="l-lead">NSX is the build-and-deploy vehicle for Ambiq's Helia tooling. Bring a model,
choose a runtime path, and measure it on silicon.</p>
</div>

<div class="l-grid l-grid--3" markdown>

<div class="l-card l-card--link" markdown>
:material-chip:{ .l-card__icon }
### heliaRT
An optimized LiteRT runtime tuned for Cortex-M cores and Apollo silicon.
[Open docs](https://ambiqai.github.io/helia-rt/){ .l-card__link }
</div>

<div class="l-card l-card--link" markdown>
:material-code-braces:{ .l-card__icon }
### heliaAOT
Ahead-of-time C generation for compact, dependency-light deployment.
[Open docs](https://ambiqai.github.io/helia-aot/){ .l-card__link }
</div>

<div class="l-card l-card--link" markdown>
:material-speedometer:{ .l-card__icon }
### heliaPROFILER
On-device model profiling to compare paths against real hardware cost.
[Open docs](https://ambiqai.github.io/helia-profiler/){ .l-card__link }
</div>

</div>

</section>

<section class="l-section" markdown>

<div class="l-section__head" markdown>
<p class="l-eyebrow">Why NSX</p>
## Built to stay inspectable
<p class="l-lead">No hidden build magic. NSX generates standard projects you can read,
edit, and reason about, then measures them where it counts.</p>
</div>

<div class="l-grid l-grid--4" markdown>

<div class="l-card" markdown>
:material-eye-outline:{ .l-card__icon }
### Transparent builds
Generated apps use CMake and Ninja, so projects stay readable and editable.
</div>

<div class="l-card" markdown>
:material-source-branch:{ .l-card__icon }
### Module resolution
Declare dependencies in YAML and lock resolved versions into the app.
</div>

<div class="l-card" markdown>
:material-developer-board:{ .l-card__icon }
### Board-ready workflow
Create, configure, build, flash, and view output for Ambiq targets.
</div>

<div class="l-card" markdown>
:material-chart-line:{ .l-card__icon }
### On-device measurement
Benchmark firmware and profile model paths against real silicon.
</div>

</div>

</section>

<div class="l-cta" markdown>

## Ready to build on Ambiq?

<p>Install the CLI, scaffold your first board app, and explore the examples.</p>

<div class="l-cta__actions" markdown>
[Install NSX](getting-started/install/index.md){ .md-button .md-button--primary }
[First app](getting-started/first-app.md){ .md-button }
[Browse examples](examples/index.md){ .md-button }
</div>

</div>

</div>
