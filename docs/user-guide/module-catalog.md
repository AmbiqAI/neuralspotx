# Module Catalog

The NSX registry ships a curated set of built-in, **first-class modules** that
cover SDK integration, platform plumbing, peripherals, profiling, and common
runtime helpers. Every module listed here is discoverable through the CLI and
eligible for normal `nsx module add` workflows.

```bash
# List the full catalog from your terminal
nsx module list --registry-only
```

> **Need a module that isn't listed here?**
>
> NSX supports **custom and third-party modules** alongside the built-in
> catalog. You can register a local directory or any git repo as a module
> for your app — no changes to the upstream registry required.
>
> See [Custom Modules](custom-modules.md) for registration commands,
> scaffolding, and end-to-end authoring guidance.

## What First-Class Means

In NSX, a first-class module is a module that is:

1. present in the packaged registry
2. discoverable through the CLI
3. eligible for normal `nsx module add` workflows
4. part of the supported, documented NSX module model

That is separate from how an app builds it. Apps still build from vendored
copies in `app/modules/` after resolution.

Useful commands:

```bash
nsx module list --registry-only
nsx module list --app-dir <app-dir>
```

---

## All Modules

Use the built-in search field above the table to filter modules, then adjust
the page size selector as needed.

Most first-class modules for the current Ambiq families are sourced from the
unified `nsx-ambiq-sdk` monorepo. That includes the SDK providers, HAL/BSP
wrappers, CMSIS/startup integration, and most common runtime and peripheral
modules across the `r3`, `r4`, and `r5` lines.

Only a small set of first-class modules are currently sourced from separate
repositories, notably `nsx-pmu-armv8m`, `nsx-cmsis-nn`, `nsx-helia-rt`,
`nsx-nanopb`, and the packaged board/tooling content that ships directly from
`neuralspotx`.

| Module | Category | Description | SoC Support |
| --- | --- | --- | --- |
| `nsx-ambiqsuite-r3` | :material-package-variant: SDK | Unified AmbiqSuite SDK provider for Apollo3 and Apollo3P targets. | Apollo3, Apollo3P |
| `nsx-ambiqsuite-r4` | :material-package-variant: SDK | Unified AmbiqSuite SDK provider for Apollo4L and Apollo4P targets. | Apollo4L, Apollo4P |
| `nsx-ambiqsuite-r5` | :material-package-variant: SDK | Unified AmbiqSuite SDK provider for Apollo330P, Apollo510, Apollo510B, Apollo510L, and Apollo5B targets. | Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
| `nsx-ambiq-hal-r3` | :material-package-variant: SDK | HAL wrapper surface for the unified `r3` SDK line. | Apollo3, Apollo3P |
| `nsx-ambiq-hal-r4` | :material-package-variant: SDK | HAL wrapper surface for the unified `r4` SDK line. | Apollo4L, Apollo4P |
| `nsx-ambiq-hal-r5` | :material-package-variant: SDK | HAL wrapper surface for the unified `r5` SDK line. | Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
| `nsx-ambiq-bsp-r3` | :material-package-variant: SDK | Board-support wrapper surface for the unified `r3` SDK line. | Apollo3, Apollo3P |
| `nsx-ambiq-bsp-r4` | :material-package-variant: SDK | Board-support wrapper surface for the unified `r4` SDK line. | Apollo4L, Apollo4P |
| `nsx-ambiq-bsp-r5` | :material-package-variant: SDK | Board-support wrapper surface for the unified `r5` SDK line. | Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
| `nsx-ambiq-usb-r4` | :material-package-variant: SDK | USB integration layer bundled with the unified `r4` SDK line. | Apollo4P |
| `nsx-ambiq-usb-r5` | :material-package-variant: SDK | USB integration layer bundled with the unified `r5` SDK line. | Apollo510, Apollo510B, Apollo5B |
| `nsx-cmsis-core` | :material-chip: Platform | CMSIS core support and integration from the unified SDK stack. | All |
| `nsx-tooling` | :material-wrench: Tooling | CLI-generated app CMake/tooling integration. | All |
| `nsx-soc-hal` | :material-chip: Platform | Shared SoC-level HAL integration layer for NSX targets. | All |
| `nsx-cmsis-startup` | :material-chip: Platform | CMSIS startup integration — vector tables, startup code, early boot wiring. | All |
| `nsx-core` | :material-cog: Runtime | Core runtime initialization and baseline support for most NSX apps. | All |
| `nsx-perf` | :material-speedometer: Profiling | Generic performance measurement helpers for timing and lightweight profiling. | All |
| `nsx-power` | :material-expansion-card: Peripheral | Power-management helpers — sleep policy, shutdown control, low-power workflows. | Apollo3, 3P, 4L, 4P, 330P, 510, 510B, 510L |
| `nsx-uart` | :material-expansion-card: Peripheral | UART wrapper for serial communication, console I/O, and host-device links. | All |
| `nsx-i2c` | :material-expansion-card: Peripheral | I2C wrapper for integrating sensors and peripherals over the I2C bus. | All |
| `nsx-spi` | :material-expansion-card: Peripheral | SPI wrapper for talking to SPI-attached devices and peripherals. | All |
| `nsx-audio` | :material-expansion-card: Peripheral | PDM audio capture driver with DMA-backed sampling and callback delivery. | Apollo5B, 510, 510B |
| `nsx-usb` | :material-expansion-card: Peripheral | USB CDC serial driver using TinyUSB with proper error handling. | Apollo5B, 510, 510B, 4P |
| `nsx-nanopb` | :material-library: Library | Vendored nanopb — zero-dynamic-memory Protocol Buffers in ANSI C. | All |
| `nsx-pmu-armv8m` | :material-speedometer: Profiling | Armv8-M PMU helpers for hardware counter configuration, capture, and transport. | Apollo5B, 510, 510B, 330P |
| `nsx-cmsis-nn` | :material-brain: ML | heliaCORE kernels and NSX integration for ML inference workloads. | Apollo5B, Apollo510, Apollo510B, Apollo510L |
| `nsx-helia-rt` | :material-brain: ML | Helia runtime integration for NSX-managed inference applications. | Apollo5B, Apollo510, Apollo510B, Apollo510L |

## Module Families

The catalog is easier to navigate if you read it by role rather than by raw
module name.

### SDK Provider Modules

These define the upstream SDK family and revision used by the rest of the
dependency graph.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiqsuite-r3`, `nsx-ambiqsuite-r4`, `nsx-ambiqsuite-r5` | Unified AmbiqSuite provider selection by release family. | Select the SDK baseline for a target and downstream wrapper stack. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules) |

### SDK Wrapper and Platform Integration Modules

These adapt raw SDK content into the NSX build and target model.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiq-hal-r3`, `nsx-ambiq-hal-r4`, `nsx-ambiq-hal-r5` | HAL wrapper surface for each unified AmbiqSuite release family. | Pull in supported HAL utilities without wiring raw SDK files by hand. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules) |
| `nsx-ambiq-bsp-r3`, `nsx-ambiq-bsp-r4`, `nsx-ambiq-bsp-r5` | BSP wrapper surface for each unified AmbiqSuite release family. | Board-support wiring layered on top of the chosen SDK release family. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules) |
| `nsx-soc-hal` | Shared SoC-level integration across targets. | Common SoC policy and low-level platform integration. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-soc-hal) |
| `nsx-cmsis-core`, `nsx-cmsis-startup` | CMSIS core and startup integration for NSX targets. | Core CMSIS headers plus startup files, vector-table wiring, and common boot integration. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules) |

### Board Modules

Board modules are selected automatically when you create an app for a specific
target. They capture board-level wiring and pin configuration.

This table has its own search and pagination controls.

| Board Module | SoC Family |
| --- | --- |
| `nsx-board-apollo3-evb` | Apollo3 |
| `nsx-board-apollo3-evb-cygnus` | Apollo3 |
| `nsx-board-apollo3p-evb` | Apollo3P |
| `nsx-board-apollo3p-evb-cygnus` | Apollo3P |
| `nsx-board-apollo330mp-evb` | Apollo330P |
| `nsx-board-apollo4l-evb` | Apollo4L |
| `nsx-board-apollo4l-blue-evb` | Apollo4L |
| `nsx-board-apollo4p-evb` | Apollo4P |
| `nsx-board-apollo4p-blue-kbr-evb` | Apollo4P |
| `nsx-board-apollo4p-blue-kxr-evb` | Apollo4P |
| `nsx-board-apollo510-evb` | Apollo510 |
| `nsx-board-apollo510b-evb` | Apollo510B |
| `nsx-board-apollo510dl-evb` | Apollo510L |
| `nsx-board-apollo5b-evb` | Apollo5B |

Board modules are first-class because they are packaged and registry-backed,
but they are usually selected indirectly through app creation or target
configuration rather than being added manually.

### Runtime and Helper Modules

These make up the common reusable runtime layer for NSX apps.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-core` | Common runtime initialization and baseline app support. | Almost every NSX app uses this directly or indirectly. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-core) |
| `nsx-tooling` | Generated app CMake and tooling integration packaged from `neuralspotx`. | Internal CLI-generated app support and helper wiring. | [GitHub](https://github.com/AmbiqAI/neuralspotx/tree/main/src/neuralspotx/cmake) |

Migration-friendly portable helpers such as `nsx_printf`, `nsx_delay_us`, and
interrupt master enable/disable now live in `nsx-core` directly rather than in
a separate first-class `nsx-portable-api` module.

### Profiling and Instrumentation Modules

These are the current first-class path for performance instrumentation.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-perf` | Generic performance capture helpers such as DWT or related profiling support. | Perf bring-up, benchmarking, and runtime instrumentation. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-perf) |
| `nsx-pmu-armv8m` | Armv8-M PMU configuration, presets, capture, and transport support. | Function-, layer-, and model-level PMU workflows on supported cores. | [GitHub](https://github.com/AmbiqAI/nsx-pmu-armv8m) |

### External First-Class Modules

These are still part of the built-in NSX catalog, but they are sourced from
separate upstream repositories instead of the unified `nsx-ambiq-sdk` monorepo.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-pmu-armv8m` | Armv8-M PMU configuration, presets, capture, and transport support. | Hardware-counter-based profiling on supported M55-class targets. | [GitHub](https://github.com/AmbiqAI/nsx-pmu-armv8m) |
| `nsx-cmsis-nn` | heliaCORE kernels and NSX integration for ML inference workloads. | Accelerated neural-network kernels for inference apps. | [GitHub](https://github.com/AmbiqAI/ns-cmsis-nn) |
| `nsx-helia-rt` | Helia runtime integration for NSX-managed inference applications. | Runtime support for Helia-based inference deployments. | [GitHub](https://github.com/AmbiqAI/helia-rt) |
| `nsx-nanopb` | Vendored nanopb with NSX packaging metadata. | Protocol Buffers support for RPC and host/device message transport. | [GitHub](https://github.com/AmbiqAI/nsx-nanopb) |

### Peripheral and Bus Modules

These expose common device and board-access surfaces without forcing those
helpers into the baseline runtime core.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-power` | Power-policy and sleep-oriented helpers. | Low-power behavior, block shutdown control, and power-state utilities. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-power) |
| `nsx-i2c` | I2C wrapper and related helpers. | Sensor and peripheral bring-up over I2C. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-i2c) |
| `nsx-spi` | SPI wrapper and related helpers. | SPI device bring-up and integration. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-spi) |
| `nsx-uart` | UART wrapper and related helpers. | Serial communication, console, or bridge workflows. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/main/modules/nsx-uart) |

Legacy `nsx-peripherals` is no longer a first-class packaged module. Its useful
pieces were retired into focused unified surfaces such as `nsx-power`,
`nsx-psram`, and board button facts layered on `nsx-gpio`.

## What Is Not First-Class Yet

Some module candidates are not part of the packaged catalog yet. That usually
means they are still app-local custom registrations, local development modules,
or future migration targets from legacy `neuralSPOT`.

---

## Working with Modules

### Add a module to your app

```bash
nsx module add nsx-uart --app-dir my-app
```

NSX resolves the full dependency closure, validates board/SoC compatibility,
and vendors the module into `my-app/modules/`.

### Inspect a module

```bash
nsx module describe nsx-audio
```

### Search by keyword

```bash
nsx module search "uart serial"
```

### Remove a module

```bash
nsx module remove nsx-uart --app-dir my-app
```

---

## Related Pages

- [Modules Overview](modules.md) — terminology and CLI workflows
- [Custom Modules](custom-modules.md) — register, scaffold, and validate third-party or local modules
- [Module Model](../architecture/module-model.md) — architecture deep-dive
