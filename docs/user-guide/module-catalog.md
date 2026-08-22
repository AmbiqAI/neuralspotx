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
cd <app-dir>
nsx module list --app-dir .
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
repositories, notably `nsx-pmu-armv8m`, `arm-cmsis-nn`, `nsx-tflite-micro`,
`nsx-cmsis-nn`, `nsx-helia-rt`, `nsx-nanopb`, `helia-dsp`, `nsx-physiokit`,
`nsx-tileio-ble`, `nsx-tileio-usb`, `nsx-sensors`, `nsx-ethos-u-driver`, and
the packaged board/tooling content that ships directly from `neuralspotx`.

| Module | Category | Description | SoC Support |
| --- | --- | --- | --- |
| `nsx-ambiqsuite` | :material-package-variant: SDK | Unified AmbiqSuite SDK provider covering all supported Apollo SoCs. | Apollo2, Apollo3, Apollo3P, Apollo4L, Apollo4P, Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
| `nsx-ambiq-hal` | :material-package-variant: SDK | Unified HAL wrapper surface (per-SoC capability-gated). | All Apollo SoCs |
| `nsx-ambiq-bsp` | :material-package-variant: SDK | Unified board-support wrapper surface. | All Apollo SoCs |
| `nsx-ambiq-usb` | :material-package-variant: SDK | Unified TinyUSB substrate; SoC-family DCD selected at configure time. | Apollo4P, Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
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
| `nsx-cordio` | :material-bluetooth: Wireless | Cordio/WSF Bluetooth LE host stack (HCI/DM/L2CAP/ATT/SMP/GATT), vendored from AmbiqSuite third_party and built from source per-SoC transport. | Apollo3, 3P, 4P, 510B |
| `nsx-ble` | :material-bluetooth: Wireless | App-facing BLE convenience API — define a GATT service with read/write/notify characteristics on top of `nsx-cordio`. | Apollo3, 3P, 4P, 510B |
| `nsx-freertos` | :material-cog: Runtime | Optional FreeRTOS kernel middleware — vendors a pinned upstream FreeRTOS-Kernel and builds the SoC-selected CMSIS port. | Apollo3P, 4P, 510, 510B, 330P, 510L |
| `nsx-nanopb` | :material-library: Library | Vendored nanopb — zero-dynamic-memory Protocol Buffers in ANSI C. | All |
| `nsx-pmu-armv8m` | :material-speedometer: Profiling | Armv8-M PMU helpers for hardware counter configuration, capture, and transport. | Apollo5B, 510, 510B, 330P |
| `arm-cmsis-nn` | :material-brain: ML | Standard Arm CMSIS-NN kernels exposed as an NSX CMake target for TFLM consumers. | All |
| `nsx-tflite-micro` | :material-brain: ML | Helia-RT TensorFlow Lite Micro runtime adapter with reference and standard Arm CMSIS-NN backends. | All |
| `nsx-cmsis-nn` | :material-brain: ML | heliaCORE kernels and NSX integration for ML inference workloads. | Apollo5B, Apollo510, Apollo510B, Apollo510L |
| `nsx-helia-rt` | :material-brain: ML | Helia runtime integration for NSX-managed inference applications. | Apollo5B, Apollo510, Apollo510B, Apollo510L |
| `nsx-ethos-u-driver` | :material-brain: ML | NSX integration of Arm's Ethos-U core driver — wraps the vendored upstream `ethos-u-core-driver` with NSX build glue, CMSIS-based cache coherency hooks, a board-supplied IRQ shim, and inference begin/end probes. Runtime-agnostic. | All (board/SoC-agnostic; a board opts in by setting `NSX_HAS_NPU=1` and supplying the NPU base address and IRQ number) |
| `nsx-npu` | :material-brain: ML | Atomiq110 glue for the Arm Ethos-U85 NPU — power-domain sequencing, IRQ wiring, and performance-mode selection on top of `nsx-ethos-u-driver`. | Atomiq110 |
| `helia-dsp` | :material-function-variant: DSP | NSX-packaged helia-dsp fork of CMSIS-DSP — FFT, filtering, and statistics kernels. | All |
| `nsx-physiokit` | :material-heart-pulse: Biosignals | Physiologic signal-processing primitives for ECG, PPG, respiration, IMU, and HRV workflows. | All |
| `nsx-tileio-ble` | :material-bluetooth: Wireless | Tileio BLE transport wrapper on top of `nsx-ble`. | Apollo3, 3P, 510B, 4P Blue |
| `nsx-tileio-usb` | :material-usb: Peripheral | Tileio USB transport wrapper on top of `nsx-usb`. | Apollo4P, 330P, 510, 510B, 510L |
| `nsx-sensors` | :material-expansion-card: Peripheral | Reusable external I2C/SPI-attached sensor and accessory drivers (MAX86150, MPU6050, ICM-45605, INA228, LED Stick) with a consistent context-based init pattern. | Apollo3, 3P, 4L, 4P, 330P, 510, 510B, 510L |

## Module Families

The catalog is easier to navigate if you read it by role rather than by raw
module name.

### SDK Provider Modules

These define the upstream SDK family and revision used by the rest of the
dependency graph.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiqsuite` | :material-package-variant: SDK | Unified AmbiqSuite SDK provider covering all supported Apollo SoCs. | Apollo2, Apollo3, Apollo3P, Apollo4L, Apollo4P, Apollo330P, Apollo510, Apollo510B, Apollo510L, Apollo5B |
| `nsx-ambiq-hal` | :material-package-variant: SDK | Unified HAL wrapper surface (per-SoC capability-gated). | All Apollo SoCs |
| `nsx-ambiq-bsp` | :material-package-variant: SDK | Unified board-support wrapper surface. | All Apollo SoCs |

### SDK Wrapper and Platform Integration Modules

These adapt raw SDK content into the NSX build and target model.

| Module family | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ambiq-hal` | Unified HAL wrapper surface (per-SoC capability-gated). | Pull in supported HAL utilities without wiring raw SDK files by hand. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules) |
| `nsx-ambiq-bsp` | Unified BSP wrapper surface. | Board-support wiring layered on top of the SDK provider. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules) |
| `nsx-soc-hal` | Shared SoC-level integration across targets. | Common SoC policy and low-level platform integration. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-soc-hal) |
| `nsx-cmsis-core`, `nsx-cmsis-startup` | CMSIS core and startup integration for NSX targets. | Core CMSIS headers plus startup files, vector-table wiring, and common boot integration. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules) |

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
| `nsx-core` | Common runtime initialization and baseline app support. | Almost every NSX app uses this directly or indirectly. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-core) |
| `nsx-tooling` | Generated app CMake and tooling integration packaged from `neuralspotx`. | Internal CLI-generated app support and helper wiring. | [GitHub](https://github.com/AmbiqAI/neuralspotx/tree/main/src/neuralspotx/cmake) |
| `nsx-freertos` | Optional FreeRTOS kernel middleware — vendors a pinned upstream FreeRTOS-Kernel and builds the SoC-selected CMSIS port. Kernel/heap policy and `FreeRTOSConfig.h` stay app-owned. | Opt-in preemptive scheduling for apps that need it (e.g. `ble_webble`). | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-freertos) |

Migration-friendly portable helpers such as `nsx_printf`, `nsx_delay_us`, and
interrupt master enable/disable now live in `nsx-core` directly rather than in
a separate first-class `nsx-portable-api` module.

### Profiling and Instrumentation Modules

These are the current first-class path for performance instrumentation.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-perf` | Generic performance capture helpers such as DWT or related profiling support. | Perf bring-up, benchmarking, and runtime instrumentation. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-perf) |
| `nsx-pmu-armv8m` | Armv8-M PMU configuration, presets, capture, and transport support. | Function-, layer-, and model-level PMU workflows on supported cores. | [GitHub](https://github.com/AmbiqAI/nsx-pmu-armv8m) |

### External First-Class Modules

These are still part of the built-in NSX catalog, but they are sourced from
separate upstream repositories instead of the unified `nsx-ambiq-sdk` monorepo.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-pmu-armv8m` | Armv8-M PMU configuration, presets, capture, and transport support. | Hardware-counter-based profiling on supported M55-class targets. | [GitHub](https://github.com/AmbiqAI/nsx-pmu-armv8m) |
| `arm-cmsis-nn` | Standard Arm CMSIS-NN kernels exposed as `nsx::arm_cmsis_nn`. | CMSIS-NN kernels for TFLM and portable Arm kernel benchmarking. | [arm-cmsis-nn](https://github.com/AmbiqAI/arm-cmsis-nn/tree/v0.1.0) |
| `nsx-tflite-micro` | Helia-RT TensorFlow Lite Micro runtime adapter with reference and standard Arm CMSIS-NN backends. | TFLM inference and runtime profiling on NSX targets. | [nsx-tflite-micro](https://github.com/AmbiqAI/nsx-tflite-micro/tree/v0.1.0) |
| `nsx-cmsis-nn` | heliaCORE kernels and NSX integration for ML inference workloads. | Accelerated neural-network kernels for inference apps. | [ns-cmsis-nn](https://github.com/AmbiqAI/ns-cmsis-nn/tree/v7.29.2) |
| `nsx-helia-rt` | Helia runtime integration for NSX-managed inference applications. | Runtime support for Helia-based inference deployments. | [GitHub](https://github.com/AmbiqAI/helia-rt) |
| `nsx-nanopb` | Vendored nanopb with NSX packaging metadata. | Protocol Buffers support for RPC and host/device message transport. | [nsx-nanopb](https://github.com/AmbiqAI/nsx-nanopb/tree/v0.1.1) |
| `helia-dsp` | NSX-packaged helia-dsp fork of CMSIS-DSP, preserving upstream Source/ CMake as the single source of truth. Distribution `v1.0.0` carries the CMSIS-DSP `1.17.x` API/payload lineage. | Signal processing, feature extraction, and FFT/filtering kernels for embedded DSP workloads. | [helia-dsp](https://github.com/AmbiqAI/helia-dsp/tree/v1.0.0) |
| `nsx-physiokit` | Physiologic signal-processing primitives for ECG, PPG, respiration, IMU, and HRV workflows, built on `helia-dsp`. | Wearable-vitals prototyping, heart-rate/respiration analytics, and embedded biosignal preprocessing. | [nsx-physiokit](https://github.com/AmbiqAI/nsx-physiokit/tree/v0.1.0) |
| `nsx-tileio-ble` | Tileio BLE transport wrapper on top of `nsx-ble`. | Stream Tileio slot data and UIO state over BLE GATT notifications. | [nsx-tileio](https://github.com/AmbiqAI/nsx-tileio/tree/v0.1.0) |
| `nsx-tileio-usb` | Tileio USB transport wrapper on top of `nsx-usb`. | Stream Tileio slot data and UIO updates over a USB vendor transport. | [nsx-tileio](https://github.com/AmbiqAI/nsx-tileio/tree/v0.1.0) |
| `nsx-ethos-u-driver` | NSX integration of Arm's Ethos-U core driver, exposed as `nsx::ethos_u_driver`. | Ethos-U NPU dispatch for HeliaAOT, HeliaRT, TFLM, and bespoke C runtimes. | [nsx-ethos-u-driver](https://github.com/AmbiqAI/nsx-ethos-u-driver/tree/nsx-ethos-u-driver-v0.1.1) |

### NPU / ML Acceleration Modules

Ethos-U NPU support spans two modules that live in two different repositories:
a runtime-agnostic core-driver integration sourced from its own standalone
repo, and the SoC-specific glue that lives in the `nsx-ambiq-sdk` monorepo.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-ethos-u-driver` | Runtime-agnostic wrapper around the vendored upstream `ethos-u-core-driver` (24.08), exposed as `nsx::ethos_u_driver`. Supplies NSX build glue plus weak overrides for CMSIS cache coherency (`ethosu_flush_dcache`/`ethosu_invalidate_dcache` via `SCB_CleanDCache_by_Addr`/`SCB_InvalidateDCache_by_Addr`), a board-supplied IRQ shim (`nsx_ethos_u_init()`/`nsx_ethos_u_irq()`), identity address remap, and default `ethosu_inference_begin`/`ethosu_inference_end` probes. Requires `nsx-cmsis-core`, `nsx-core`, and `nsx-soc-hal`. | Ethos-U55/U65/U85 dispatch from HeliaAOT, HeliaRT, TFLM, or a bespoke C runtime, on any board that sets `NSX_HAS_NPU=1` and supplies the NPU base address and IRQ number. | [nsx-ethos-u-driver](https://github.com/AmbiqAI/nsx-ethos-u-driver/tree/nsx-ethos-u-driver-v0.1.1) |
| `nsx-npu` | Atomiq110 glue for the Arm Ethos-U85 NPU, exposed as `nsx::npu` and layered on `nsx::ethos_u_driver`. Powers the NPU domain via `am_hal_pwrctrl_periph_enable`/`am_hal_pwrctrl_periph_disable`, owns the `am_npu_isr` → `nsx_ethos_u_irq` interrupt glue on IRQ 117, and selects the NPU performance mode via `am_hal_pwrctrl_npu_mode_select` (skippable with `skip_perf_mode` for FPGA/pre-silicon bring-up). Public API is `nsx_npu_init()`, `nsx_npu_deinit()`, and `nsx_npu_driver()`. Cache maintenance and inference probes are not here — they live in `nsx-ethos-u-driver`. | Bringing up the Ethos-U85 NPU on Atomiq110 so TFLM runtimes can dispatch Vela-compiled command streams. | [nsx-ambiq-sdk](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-npu) |

#### Cross-repo module dependencies

A module's `nsx-module.yaml` `depends.required` list can name a module that
lives in a different repository than the module itself. `nsx-npu` is the
current example: it ships from the `nsx-ambiq-sdk` monorepo but requires
`nsx-ethos-u-driver`, which has its own standalone repo. The registry lockfile
(`src/neuralspotx/data/registry.lock.yaml`) pins each module's source project
and revision independently, so the two are resolved separately and then
materialized side-by-side under `modules/` at workspace assembly time.

[examples/npu_person_detect](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/npu_person_detect)
is the consuming example. Its `nsx.yml` lists only `nsx-helia-rt` and
`nsx-npu`; `nsx-ethos-u-driver` is pulled in transitively as an `nsx-npu`
dependency rather than being requested directly.

### Peripheral and Bus Modules

These expose common device and board-access surfaces without forcing those
helpers into the baseline runtime core.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-power` | Power-policy and sleep-oriented helpers. | Low-power behavior, block shutdown control, and power-state utilities. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-power) |
| `nsx-i2c` | I2C wrapper and related helpers. | Sensor and peripheral bring-up over I2C. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-i2c) |
| `nsx-spi` | SPI wrapper and related helpers. | SPI device bring-up and integration. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-spi) |
| `nsx-uart` | UART wrapper and related helpers. | Serial communication, console, or bridge workflows. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-uart) |
| `nsx-sensors` | External I2C/SPI-attached sensor and accessory drivers (MAX86150, MPU6050, ICM-45605, INA228, LED Stick) built on `nsx-i2c`/`nsx-spi` with a consistent context-based init pattern. | Bio-sensor capture, IMU bring-up, current/voltage monitoring, simple I2C accessory control. | [nsx-sensors](https://github.com/AmbiqAI/nsx-sensors/tree/v0.1.0) |

Legacy `nsx-peripherals` is no longer a first-class packaged module. Its useful
pieces were retired into focused unified surfaces such as `nsx-power`,
`nsx-psram`, and board button facts layered on `nsx-gpio`.

### Wireless / BLE Modules

Bluetooth LE support is split into a low-level host stack and an app-facing
convenience API, so apps that only need the stack (or want to bring their own
wrapper) don't have to pull in both.

| Module | What it provides | Typical use | More info |
| --- | --- | --- | --- |
| `nsx-cordio` | Cordio/WSF BLE host stack (HCI/DM/L2CAP/ATT/SMP/GATT), vendored from AmbiqSuite third_party and built per-SoC transport (Cooper, integrated BLE, EM9305). | Low-level BLE host stack for higher-level BLE wrappers. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-cordio) |
| `nsx-ble` | App-facing BLE convenience API ported from legacy neuralSPOT `ns-ble`; define a GATT service with read/write/notify characteristics on top of `nsx-cordio`. | Stand up a single BLE GATT service with minimal source changes from legacy `ns-ble` apps. | [GitHub](https://github.com/AmbiqAI/nsx-ambiq-sdk/tree/v5.2.24/modules/nsx-ble) |

## What Is Not First-Class Yet

Some module candidates are not part of the packaged catalog yet. That usually
means they are still app-local custom registrations, local development modules,
or future migration targets from legacy `neuralSPOT`.

---

## Working with Modules

### Add a module to your app

```bash
cd my-app
nsx module add nsx-uart
```

NSX resolves the full dependency closure, validates board/SoC compatibility,
and vendors the module into `my-app/modules/`.

### Inspect a module

```bash
nsx module describe nsx-audio
```

### Search by keyword

```bash
nsx module search "uart serial" --app-dir .
```

### Remove a module

```bash
cd my-app
nsx module remove nsx-uart
```

---

## Related Pages

- [Modules Overview](modules.md) — terminology and CLI workflows
- [Custom Modules](custom-modules.md) — register, scaffold, and validate third-party or local modules
- [Module Model](../architecture/module-model.md) — architecture deep-dive
