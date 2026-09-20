---
title: Next steps
description: Where to go once your first app builds and runs, across the guides, the module catalog, the examples and the reference.
---

Your app scaffolds, configures, builds and, if you have a board, runs. From here the
documentation splits by what you want to do next.

## Change what the app is made of

Every app is a board plus a set of modules, declared in `nsx.yml` and pinned in
`nsx.lock`.

- The [module catalog](/neuralspotx/modules/catalog/) is the filterable list of all 50
  modules: what each one provides, which SoCs and boards it declares compatibility with,
  and the `nsx module add` line that pulls it in.
- The [board matrix](/neuralspotx/modules/boards/) lists the 17 packaged boards with their
  SoC, tier, SDK provider, CPU and declared toolchains.
- [`nsx module`](/neuralspotx/reference/cli/module/) adds, removes, lists, searches and
  describes modules. [`nsx lock`](/neuralspotx/reference/cli/lock/) and
  [`nsx sync`](/neuralspotx/reference/cli/sync/) are the two halves of that job when you
  want to run them separately, and [`nsx outdated`](/neuralspotx/reference/cli/outdated/)
  and [`nsx update`](/neuralspotx/reference/cli/update/) deal with upstream drift.

:::note[Compatibility is declared, not measured]
Everything the catalog says about which SoCs and boards a module supports comes from that
module's own manifest. It is a declaration by the module author, not a statement that the
combination has been run on hardware.
:::

## Go deeper on the workflow

- The [Guides](/neuralspotx/guides/) section covers the app model and layout, module
  workflows, memory placement, startup and linker behavior, toolchain selection, and the
  concepts behind app generation.
- The [CLI reference](/neuralspotx/reference/cli/) has a page per command and subcommand,
  generated from the argument parser, so it always matches the version you installed.
- The [configuration reference](/neuralspotx/reference/config/) documents the schemas:
  [`nsx.yml`](/neuralspotx/reference/config/nsx-yml/),
  [`nsx-module.yaml`](/neuralspotx/reference/config/nsx-module-yaml/),
  [`board.yaml`](/neuralspotx/reference/config/board-yaml/) and
  [`nsx.lock`](/neuralspotx/reference/config/nsx-lock/).

## Drive NSX from code

Everything the CLI does is available as a Python API, which is how you script a build
matrix or wire NSX into another tool. See the
[Python API reference](/neuralspotx/reference/api/). Every public symbol is currently
marked provisional, so pin your NSX version if you depend on it.

For agents and scripts that would rather not parse help text,
[`nsx commands --json`](/neuralspotx/reference/cli/commands/) returns the whole command
tree, and [`nsx doctor --json`](/neuralspotx/reference/cli/doctor/) returns the
environment report.

## Read working apps

The repository ships ten maintained example apps covering FreeRTOS, CoreMark, BLE, audio
capture, USB, ML inference, PMU profiling and power measurement. Until they move onto this
site they live in
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples) in the
repository. From a source checkout you can build any of them by name, because the
positional app argument resolves under `./examples`:

```bash
nsx build hello_world --board apollo510_evb
```

## Coming from neuralSPOT

[Migrating from neuralSPOT](/neuralspotx/getting-started/migrate-from-neuralspot/) maps
the legacy packages onto NSX modules and says which ones have no equivalent yet.
