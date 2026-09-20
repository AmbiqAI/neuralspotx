---
title: Migrating from neuralSPOT
description: How legacy neuralSPOT packages map onto NSX modules, what has moved, what was split, and what has no equivalent yet.
---

NSX is a modular replacement for the parts of legacy `neuralSPOT` that matter for current
Ambiq bare-metal work: bring-up, build, profiling and device integration. It is not a
one-to-one repackaging, and it does not try to be.

The approach is to preserve capabilities rather than package boundaries. Large,
opinionated legacy modules get split into smaller NSX modules where that improves reuse,
and anything app-specific stays optional rather than joining the baseline.

## What NSX covers today

The migrated core is the baseline you need to create an app, configure and build it
reproducibly, flash and inspect it on hardware, bring up common board peripherals, and run
profiling and instrumentation. That is why the first wave centered on
[`nsx-core`](/neuralspotx/modules/nsx-core/),
[`nsx-perf`](/neuralspotx/modules/nsx-perf/),
[`nsx-pmu-armv8m`](/neuralspotx/modules/nsx-pmu-armv8m/),
[`nsx-power`](/neuralspotx/modules/nsx-power/),
[`nsx-i2c`](/neuralspotx/modules/nsx-i2c/),
[`nsx-spi`](/neuralspotx/modules/nsx-spi/),
[`nsx-uart`](/neuralspotx/modules/nsx-uart/),
[`nsx-soc-hal`](/neuralspotx/modules/nsx-soc-hal/),
[`nsx-cmsis-startup`](/neuralspotx/modules/nsx-cmsis-startup/),
[`nsx-ambiq-hal`](/neuralspotx/modules/nsx-ambiq-hal/) and
[`nsx-ambiq-bsp`](/neuralspotx/modules/nsx-ambiq-bsp/).

It does not yet carry every legacy application stack.

## Refactoring direction

Several legacy modules carried assumptions about examples, transport choices, power
behavior or application structure. NSX keeps the useful parts while making the modules
less opinionated:

1. Mixed-purpose utility bundles are split into focused modules.
2. Explicit metadata and dependency closure replace implicit coupling.
3. Board and SDK specifics stay in wrapper modules.
4. Optional connectivity, sensor and ML stacks stay out of the baseline unless they are
   broadly useful.
5. Small, stable APIs are preferred, so the same surface serves smoke tests, examples and
   product code.

You can see the result in the current module set: legacy PMU and perf helpers came out of
`ns-utils` into `nsx-pmu-armv8m` and `nsx-perf`; power gained a first-class home in
`nsx-power`; mixed peripheral helpers were retired into focused surfaces; and SDK
consumption is split across provider, HAL, BSP, startup and SoC modules instead of being
buried in app code.

## Migration matrix

Status meanings:

- **Migrated**: a first-class NSX replacement exists.
- **Split**: the capability exists but is spread across several NSX modules.
- **Partial**: some of the capability exists; the replacement is incomplete.
- **Future**: no NSX replacement yet.
- **Dropped**: a decision was made not to migrate it.

| Legacy module | Status | NSX home | Notes |
| --- | --- | --- | --- |
| `ns-core` | Migrated | [`nsx-core`](/neuralspotx/modules/nsx-core/) | Core runtime and bring-up surface. |
| `ns-harness` | Split | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m` | Print, delay and interrupt shims moved into `nsx-core`; profiling into `nsx-perf` and `nsx-pmu-armv8m`. TFLM `DebugLog` registration is superseded by heliaRT's own implementation. The remaining gap is packaging only: the `MicroProfilerInterface` glue (`NsxPmuProfiler`) still lives in the `kws_infer` example rather than in a reusable module. |
| `ns-i2c` | Migrated | [`nsx-i2c`](/neuralspotx/modules/nsx-i2c/) | Bus wrapper and register-driver helpers. The sample device drivers (MPU6050, MAX86150) moved to [`nsx-sensors`](/neuralspotx/modules/nsx-sensors/). |
| `ns-spi` | Migrated | [`nsx-spi`](/neuralspotx/modules/nsx-spi/) | SPI wrapper support. |
| `ns-uart` | Migrated | [`nsx-uart`](/neuralspotx/modules/nsx-uart/) | UART wrapper support. |
| `ns-features` | Future | none | The quaternion and Euler feature-extraction helpers have not been ported. |
| `ns-peripherals` | Migrated | `nsx-power`, `nsx-psram`, board button facts on `nsx-gpio` | The mixed legacy bucket was retired into focused surfaces rather than kept under one name. |
| `ns-utils` | Split | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m`, `nsx-power` | The portable helpers (`nsx_printf`, `nsx_delay_us`, interrupt enable and disable) live directly in `nsx-core`. |
| `ns-ble` | Migrated | [`nsx-ble`](/neuralspotx/modules/nsx-ble/) with [`nsx-cordio`](/neuralspotx/modules/nsx-cordio/) | An early baseline: one service and one connection, no out-of-band pairing. The `ble_webble` example exercises it across the CI build matrix. |
| `ns-usb` | Migrated | [`nsx-usb`](/neuralspotx/modules/nsx-usb/) | USB CDC serial on TinyUSB. |
| `ns-imu` | Partial | [`nsx-sensors`](/neuralspotx/modules/nsx-sensors/) | The ICM-45605 driver was ported at TDK basic-driver scope. The rest of the generic `ns-imu` wrapper was deliberately not carried forward. |
| `ns-audio` | Migrated | [`nsx-audio`](/neuralspotx/modules/nsx-audio/) | PDM capture with DMA-backed sampling and callback delivery. |
| `ns-physiokit` | Migrated | [`nsx-physiokit`](/neuralspotx/modules/nsx-physiokit/) | Biosignal primitives for ECG, PPG, respiration and HRV, built on `helia-dsp`. |
| `ns-tileio` | Migrated | [`nsx-tileio-ble`](/neuralspotx/modules/nsx-tileio-ble/), [`nsx-tileio-usb`](/neuralspotx/modules/nsx-tileio-usb/) | Split by transport, with Python host tools. |
| `ns-camera` | Future | none | Narrow, app-specific demo hardware (Arducam Mega over SPI, Apollo4 only). A direct port is probably not worth it. |
| `ns-ipc` | Dropped | none | Not migrated. |
| `ns-model` | Dropped | none | Not migrated. |
| `ns-nnsp` | Dropped | none | Not migrated. |
| `ns-rpc` | Dropped | none | Not migrated. [`nsx-nanopb`](/neuralspotx/modules/nsx-nanopb/) is available as a protobuf framing building block if a transport wrapper is revisited. |

:::note[Two names in that table have no catalog page]
`nsx-gpio` and `nsx-psram` are vendored inside the `nsx-ambiq-sdk` monorepo rather than
registered as standalone entries, so they do not appear in the
[module catalog](/neuralspotx/modules/catalog/). They are still real modules you can
depend on.
:::

## Deciding whether to migrate something

Before porting a legacy module, ask:

1. Does it help lightweight bare-metal NSX apps?
2. Is it generic enough to serve more than one app or demo?
3. Can it be expressed with a smaller, less opinionated API surface?
4. Is it better as an optional module than as a baseline dependency?
5. Does it fit the NSX module model cleanly?

Mostly yes means it is a good candidate.

## Where NSX already replaces the legacy core

Board bring-up, smoke tests, the build and flash and view workflow, common peripheral
access, and profiling and PMU instrumentation. Chasing broad legacy parity for its own
sake is not the goal; simplifying the old module boundaries as they move is.
