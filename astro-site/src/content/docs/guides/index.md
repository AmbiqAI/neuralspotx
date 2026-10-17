---
title: User guide
description: Build and maintain NSX applications, manage modules, configure hardware, explore examples and automate your workflow.
---

Use these guides after [building your first app](/neuralspotx/getting-started/).
Choose a task below. For exact flags, signatures and manifest fields, use the
[API reference](/neuralspotx/reference/).

## Build and run

- [App model](/neuralspotx/guides/apps/app-model/): how an application owns its sources and dependencies.
- [App layout](/neuralspotx/guides/apps/app-layout/): which files to edit, commit or regenerate.
- [Build, flash and view](/neuralspotx/guides/apps/build-flash-view/): configure firmware, program the board and capture output.
- [Troubleshooting](/neuralspotx/guides/apps/troubleshooting/): diagnose environment, dependency, build and probe failures.

## Manage modules

- [Using modules](/neuralspotx/guides/modules/using-modules/): find, add, inspect and remove capabilities.
- [Lock and sync](/neuralspotx/guides/modules/lock-and-sync/): pin dependencies and reproduce an application's source set.
- [Custom modules](/neuralspotx/guides/modules/custom-modules/): develop a module or register your own source.
- [Module catalog](/neuralspotx/modules/catalog/): search the packaged modules and their declared compatibility.

## Configure hardware and toolchains

- [Boards and targets](/neuralspotx/guides/apps/boards-and-targets/): select a board or add targets to an app.
- [Board matrix](/neuralspotx/modules/boards/): look up packaged board descriptors and toolchains.
- [Toolchains](/neuralspotx/guides/system/toolchains/): select GCC, ACFE or ATfE and check their validation status.
- [SDK foundation and overrides](/neuralspotx/guides/modules/sdk-providers/): understand HAL/BSP integration and use an alternate SDK source.

## Configure firmware

- [System initialization](/neuralspotx/guides/system/system-init/): initialize the runtime and enable debug output.
- [Memory placement](/neuralspotx/guides/system/memory-placement/): place code and data and manage caches.
- [Startup and linker](/neuralspotx/guides/system/startup-and-linker/): inspect or override the board's startup and memory layout.

## Explore examples

The [examples](/neuralspotx/guides/examples/) cover basic board bring-up, individual
capabilities and integrations. Each page includes build instructions and declared target
status. Start with an example close to your application, then inspect its manifest.

## Automate your workflow

- [Python API guide](/neuralspotx/guides/python-api/): call NSX operations and handle typed results and errors.
- [Automation and agents](/neuralspotx/guides/contribute/agent-guidance/): use structured output and respect generated files.

## Understand the architecture

[Architecture concepts](/neuralspotx/guides/concepts/) explain app generation,
dependency resolution, module contracts, metadata and portability across targets.
These are background explanations; the task guides above provide the working steps.

## Extend NSX

- [Add a board](/neuralspotx/guides/contribute/adding-a-board/): implement and validate board support.
- [Contribute a module](/neuralspotx/guides/contribute/adding-a-module/): prepare a reusable module for the registry.
