---
title: Guides
description: Task guides for building apps with NSX, covering apps, modules, memory, startup, toolchains, the concepts behind app generation, the Python API and the example apps.
---

The guides cover the work that happens after your first app builds: changing what the app
is made of, deciding what goes in which memory region, understanding what the generated
startup and linker files do, and choosing a toolchain for a target.

Everything NSX generates is ordinary CMake and Ninja, so these pages explain the generated
project rather than hiding it. If you have not built anything yet, start with
[Getting started](/neuralspotx/getting-started/).

## Apps

Working with a generated app: what it is, what is in it, and what to do when it will not
build.

- [The app model](/neuralspotx/guides/apps/app-model/) - why an app vendors everything,
  and the choices `nsx create-app` asks you to make.
- [App layout](/neuralspotx/guides/apps/app-layout/) - every file and directory, when each
  appears, and which ones you may edit.
- [Build, flash and view](/neuralspotx/guides/apps/build-flash-view/) - how the five
  commands behave day to day, including the SWO reset policy.
- [Boards and targets](/neuralspotx/guides/apps/boards-and-targets/) - declaring targets
  and building one app for several boards.
- [Troubleshooting](/neuralspotx/guides/apps/troubleshooting/) - organized around the
  errors NSX actually prints.

## Modules in your app

Changing what the app is made of, and pinning it so it stays that way.

- [Using modules](/neuralspotx/guides/modules/using-modules/) - find, add, inspect and
  remove dependencies.
- [Custom modules](/neuralspotx/guides/modules/custom-modules/) - write a module of your
  own and point an app at it.
- [Lock and sync](/neuralspotx/guides/modules/lock-and-sync/) - resolution, version
  pinning, drift detection and the CI recipe.
- [SDK providers](/neuralspotx/guides/modules/sdk-providers/) - where the AmbiqSuite
  payload comes from and how to build against your own.

The [module catalog](/neuralspotx/modules/) is the generated list of every module NSX
pins, with a page each.

## System

The layer between your `main()` and the silicon.

- [System initialization](/neuralspotx/guides/system/system-init/) - the two init entry
  points and how to turn on SWO or UART output.
- [Memory placement](/neuralspotx/guides/system/memory-placement/) - put code and data
  where you meant, and manage the caches.
- [Startup and linker](/neuralspotx/guides/system/startup-and-linker/) - which startup file
  and linker script your board selects, and how to override them.
- [Toolchain support](/neuralspotx/guides/system/toolchains/) - the three cross compilers,
  how one is selected, and what differs.

## Concepts

Why NSX behaves the way it does, for when something surprises you.

- [Overview](/neuralspotx/guides/concepts/) - the five ideas, in one page.
- [App generation flow](/neuralspotx/guides/concepts/app-generation-flow/)
- [Dependency model](/neuralspotx/guides/concepts/dependency-model/)
- [Module model](/neuralspotx/guides/concepts/module-model/)
- [Metadata model](/neuralspotx/guides/concepts/metadata-model/)
- [Multi-target and portability](/neuralspotx/guides/concepts/multi-target/)

## Python API

- [Python API guide](/neuralspotx/guides/python-api/) - drive NSX from Python or from an
  agent, with typed results instead of parsed output.

## Examples

- [Examples overview](/neuralspotx/guides/examples/) - the example apps this repository
  ships, with the tier, status and boards each author declares, and a page per example
  carrying its README.

## Contribute

- [Agent guidance](/neuralspotx/guides/contribute/agent-guidance/) - the machine-readable
  surfaces and the invariants not to break.
- [Adding a board](/neuralspotx/guides/contribute/adding-a-board/)
- [Adding a module](/neuralspotx/guides/contribute/adding-a-module/)

## Reference, when a guide is not what you want

The [CLI reference](/neuralspotx/reference/cli/), the
[Python API reference](/neuralspotx/reference/api/) and the
[configuration reference](/neuralspotx/reference/config/) are generated from NSX itself, so
they always match the version you installed. These guides link into them rather than
repeating their tables.
