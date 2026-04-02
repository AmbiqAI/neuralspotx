# First-Class Modules

This page describes the first-class modules currently shipped in the packaged
NSX registry.

In NSX, a first-class module is a module that is:

1. present in the packaged registry
2. discoverable through the CLI
3. eligible for normal `nsx module add` workflows
4. part of the supported, documented NSX module model

These are different from:

1. app-local custom modules registered only for one app
2. local repos that are not yet in the packaged registry
3. experimental module candidates that have not been promoted into the standard
   catalog yet

First-class status answers: "Is this part of the supported NSX catalog?"

It does not answer: "Where does this app build it from?"
Apps still build from vendored copies in `app/modules/`.

## Useful Commands

List the packaged first-class catalog:

```bash
nsx module list --registry-only
```

List the effective catalog for a specific app and mark enabled modules:

```bash
nsx module list --app-dir <app-dir>
```

## How to Read the Catalog

The current first-class catalog is organized around a few roles:

1. SDK provider modules
2. SDK wrapper and platform integration modules
3. board modules
4. runtime and helper modules
5. profiling and instrumentation modules
6. peripheral access modules

Not every module candidate is automatically first-class. First-class status
means the module is present in the packaged registry and is available through
the standard CLI workflows.

## First-Class Module Families

### SDK Provider Modules

These modules define the upstream SDK family and revision used by the rest of
the dependency graph.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiqsuite-r3`, `nsx-ambiqsuite-r4`, `nsx-ambiqsuite-r5` | Curated AmbiqSuite provider selection by release family. | Select the SDK baseline for a target and downstream wrapper stack. | [r3](https://github.com/AmbiqAI/nsx-ambiqsuite-r3), [r4](https://github.com/AmbiqAI/nsx-ambiqsuite-r4), [r5](https://github.com/AmbiqAI/nsx-ambiqsuite-r5) |

### SDK Wrapper and Platform Integration Modules

These modules adapt raw SDK content into a cleaner NSX-facing build and target
model.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiq-hal-r3`, `nsx-ambiq-hal-r4`, `nsx-ambiq-hal-r5` | Curated HAL wrapper surface for each AmbiqSuite release family. | Pull in supported HAL utilities without wiring raw SDK files by hand. | [r3](https://github.com/AmbiqAI/nsx-ambiq-hal-r3), [r4](https://github.com/AmbiqAI/nsx-ambiq-hal-r4), [r5](https://github.com/AmbiqAI/nsx-ambiq-hal-r5) |
| `nsx-ambiq-bsp-r3`, `nsx-ambiq-bsp-r4`, `nsx-ambiq-bsp-r5` | Curated BSP wrapper surface for each AmbiqSuite release family. | Board-support wiring layered on top of the chosen SDK release family. | [r3](https://github.com/AmbiqAI/nsx-ambiq-bsp-r3), [r4](https://github.com/AmbiqAI/nsx-ambiq-bsp-r4), [r5](https://github.com/AmbiqAI/nsx-ambiq-bsp-r5) |
| `nsx-soc-hal` | Shared SoC-level integration across targets. | Common SoC policy and low-level platform integration. | [GitHub](https://github.com/AmbiqAI/nsx-soc-hal) |
| `nsx-cmsis-startup` | CMSIS and startup integration for NSX targets. | Startup files, vector-table wiring, and common boot integration. | [GitHub](https://github.com/AmbiqAI/nsx-cmsis-startup) |

### Board Modules

Board modules package board-specific configuration and defaults. They are kept
in the `neuralspotx` repo and are available through the packaged registry.

Current first-class board modules include:

1. `nsx-board-apollo3-evb`
2. `nsx-board-apollo3-evb-cygnus`
3. `nsx-board-apollo3p-evb`
4. `nsx-board-apollo3p-evb-cygnus`
5. `nsx-board-apollo330mp-evb`
6. `nsx-board-apollo4l-evb`
7. `nsx-board-apollo4l-blue-evb`
8. `nsx-board-apollo4p-evb`
9. `nsx-board-apollo4p-blue-kbr-evb`
10. `nsx-board-apollo4p-blue-kxr-evb`
11. `nsx-board-apollo510-evb`
12. `nsx-board-apollo510b-evb`
13. `nsx-board-apollo5b-evb`

High-level notes:

1. board modules are first-class because they are packaged and registry-backed
2. they capture board-level wiring and policy, not generic runtime behavior
3. they are usually selected indirectly through app creation or target config

More info:

- [Board sources in neuralspotx](https://github.com/AmbiqAI/neuralspotx/tree/main/src/neuralspotx/boards)
- [Boards and Targets](boards-and-targets.md)

### Runtime and Helper Modules

These modules make up the core reusable runtime layer for NSX apps.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-core` | Common runtime initialization and baseline app support. | Almost every NSX app uses this directly or indirectly. | [GitHub](https://github.com/AmbiqAI/nsx-core) |
| `nsx-harness` | Debug-print, low-power print, and harness-side helpers. | Bring-up, smoke tests, and instrumentation-friendly apps. | [GitHub](https://github.com/AmbiqAI/nsx-harness) |
| `nsx-utils` | Small common helpers that do not deserve their own specialized module. | Light utility needs that are broader than one board or app. | [GitHub](https://github.com/AmbiqAI/nsx-utils) |
| `nsx-portable-api` | Thin migration-friendly convenience wrappers. | Ease migration from older code or reduce direct SDK coupling in simple apps. | [GitHub](https://github.com/AmbiqAI/nsx-portable-api) |
| `nsx-tooling` | Generated app CMake/tooling integration packaged from the `neuralspotx` repo. | Internal CLI-generated app support and helper wiring. | [GitHub](https://github.com/AmbiqAI/neuralspotx/tree/main/src/neuralspotx/cmake) |

### Profiling and Instrumentation Modules

These modules are the current first-class path for performance instrumentation.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-perf` | Generic performance capture helpers such as DWT or related profiling support. | Perf bring-up, benchmarking, and runtime instrumentation. | [GitHub](https://github.com/AmbiqAI/nsx-perf) |
| `nsx-pmu-armv8m` | Armv8-M PMU configuration, presets, capture, and transport support. | Function-, layer-, and model-level PMU workflows on supported cores. | [GitHub](https://github.com/AmbiqAI/nsx-pmu-armv8m) |

### Peripheral and Bus Modules

These modules expose common device and board-access surfaces without forcing
those helpers into the baseline runtime core.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-peripherals` | Common board-peripheral helpers such as NVM or PSRAM-facing support. | Generic board peripheral access for smoke tests and small apps. | [GitHub](https://github.com/AmbiqAI/nsx-peripherals) |
| `nsx-power` | Power-policy and sleep-oriented helpers. | Low-power behavior, block shutdown control, and power-state utilities. | [GitHub](https://github.com/AmbiqAI/nsx-power) |
| `nsx-i2c` | I2C wrapper and related helpers. | Sensor and peripheral bring-up over I2C. | [GitHub](https://github.com/AmbiqAI/nsx-i2c) |
| `nsx-spi` | SPI wrapper and related helpers. | SPI device bring-up and integration. | [GitHub](https://github.com/AmbiqAI/nsx-spi) |
| `nsx-uart` | UART wrapper and related helpers. | Serial communication, console, or bridge workflows. | [GitHub](https://github.com/AmbiqAI/nsx-uart) |

## What Is Not First-Class Yet

Some module candidates are not yet part of the
packaged first-class catalog.

Examples can include:

1. modules that are available only through custom registration or local
   development workflows and are not yet in the packaged registry
2. app-local registered modules
3. future migration targets from legacy `neuralSPOT`

This distinction is important because first-class status is about discoverable,
supported registry membership, not just repository existence.

For normal app development, NSX handles source resolution and vendoring for
built-in modules. Users do not need to maintain a separate module-repo checkout
to use first-class modules.

## Related Docs

- [Modules](modules.md)
- [Module Model](../architecture/module-model.md)
- [Migrating from neuralSPOT](../architecture/migration-from-neuralspot.md)
- [Adding Modules](../contributing/adding-modules.md)
