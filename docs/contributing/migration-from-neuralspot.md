# Migrating from neuralSPOT

This page describes the high-level migration path from legacy `neuralSPOT` to
NSX.

The immediate goal is not one-to-one package parity. The immediate goal is a
clean, modular replacement for the core bring-up, build, profiling, and device
integration layers that matter for current Ambiq bare-metal workflows.

After that baseline is solid, useful legacy capabilities can move over as
optional NSX modules with cleaner boundaries and fewer baked-in assumptions.

## Migration Strategy

The current migration strategy is:

1. Migrate core platform capabilities first.
2. Preserve important capabilities rather than preserving every legacy package
   boundary.
3. Split large opinionated legacy modules into smaller first-class NSX modules
   when that improves reuse.
4. Keep starter profiles narrow and predictable.
5. Move app-specific or optional stacks into optional modules rather than the
   baseline.

In practice this means NSX is intentionally starting with:

1. board and SoC wiring
2. runtime init and harness support
3. bus wrappers and peripheral helpers
4. performance and PMU instrumentation
5. a small, inspectable app workflow

It does not yet aim to carry every legacy application stack into the default
NSX experience.

## What "Migrate Core" Means

For NSX, the current "core" migration target is the baseline required to:

1. create an app
2. configure and build it reproducibly
3. flash and inspect it on hardware
4. bring up common board peripherals
5. run profiling and instrumentation workflows

That is why the first migration wave emphasizes modules such as:

1. `nsx-core`
2. `nsx-perf`
3. `nsx-pmu-armv8m`
4. `nsx-power`
5. `nsx-i2c`
6. `nsx-spi`
7. `nsx-uart`
8. `nsx-soc-hal`
9. `nsx-cmsis-startup`
10. `nsx-ambiq-hal`
11. `nsx-ambiq-bsp`

## Refactoring Direction

Legacy `neuralSPOT` modules were useful, but several carried extra assumptions
about examples, transport choices, power behavior, or application structure.

The NSX direction is to keep the useful parts while making modules less
opinionated:

1. split mixed-purpose utility bundles into focused modules
2. prefer explicit metadata and dependency closure over implicit coupling
3. keep board and SDK specifics in wrapper modules
4. keep optional connectivity, sensor, and ML stacks out of the baseline unless
   they are broadly useful
5. favor small stable APIs that can be reused across smoke tests, examples, and
   product code

Examples already visible in the current module set:

1. legacy PMU and perf helpers were separated from `ns-utils` into
   `nsx-pmu-armv8m` and `nsx-perf`
2. legacy power functionality now has a first-class home in `nsx-power`
3. legacy mixed peripheral helpers were retired into focused surfaces such as
   `nsx-power`, `nsx-psram`, and board-owned button facts layered on `nsx-gpio`
4. platform SDK consumption is split across provider, HAL, BSP, startup, and
   SoC integration modules instead of being buried inside app code

## Migration Matrix

The table below maps the major legacy `neuralSPOT` module areas to their
current NSX status.

Status definitions:

1. `Migrated`: a clear first-class NSX replacement exists.
2. `Split`: the legacy capability exists, but is intentionally distributed
   across multiple NSX modules.
3. `Partial`: some capability exists, but there is not yet a complete
   first-class replacement.
4. `Future`: no first-class NSX replacement exists yet.

| Legacy module | NSX status | Current NSX home | Notes |
| --- | --- | --- | --- |
| `ns-core` | Migrated | `nsx-core` | Core runtime and bring-up surface are present. |
| `ns-harness` | Split | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m` | Print/delay/interrupt shims moved into `nsx-core`; perf and PMU-based profiling moved into `nsx-perf`/`nsx-pmu-armv8m`. TFLM `DebugLog` registration is superseded by `helia-rt`'s own implementation. The one remaining gap is packaging-only: the `MicroProfilerInterface` glue (`NsxPmuProfiler`) still lives only in the `kws_infer` example rather than as a reusable module. |
| `ns-i2c` | Migrated | `nsx-i2c` | Bus wrapper and register-driver helpers are available; sample device drivers (MPU6050, MAX86150) moved into `nsx-sensors`. |
| `ns-spi` | Migrated | `nsx-spi` | SPI wrapper support is available. |
| `ns-uart` | Migrated | `nsx-uart` | UART wrapper support is available. |
| `ns-features` | Future | none yet | No first-class NSX equivalent found; quaternion/Euler feature-extraction helpers have not been ported. |
| `ns-peripherals` | Migrated | `nsx-power`, `nsx-psram`, board button facts on `nsx-gpio` | The mixed legacy bucket was retired into focused unified surfaces rather than kept as a same-name module. |
| `ns-utils` | Split | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m`, `nsx-power` | Legacy utilities bundled several concerns that are now separated; portable helpers (`nsx_printf`, `nsx_delay_us`, interrupt enable/disable) live directly in `nsx-core`. |
| `ns-ble` | Migrated | `nsx-ble` (+ `nsx-cordio`) | First-class, registry-listed. Hardware-smoke validated via the `ble_webble` example (CI build matrix across GCC/armclang, 3 boards). Still an early baseline: single service/connection, no OOB pairing. |
| `ns-usb` | Migrated | `nsx-usb` | USB CDC serial driver using TinyUSB with proper error handling. |
| `ns-imu` | Partial | `nsx-sensors` (ICM-45605 only) | The ICM-45605 driver (TDK "basic driver" scope) was ported into `nsx-sensors`; the rest of the legacy `ns-imu` generic wrapper was intentionally not carried forward. |
| `ns-audio` | Migrated | `nsx-audio` | PDM audio capture driver with DMA-backed sampling and callback delivery. |
| `ns-physiokit` (separate repo) | Migrated | `nsx-physiokit` | First-class, registry-listed. Biosignal (ECG/PPG/respiration/HRV) primitives, built on `helia-dsp`. |
| `ns-tileio` (separate repo, tio-ble/tio-usb) | Migrated | `nsx-tileio-ble`, `nsx-tileio-usb` | First-class, registry-listed. Hardware validated on Apollo4 Blue Plus and Apollo510B via local bring-up apps and Python host tools. |
| `ns-camera` | Future | none yet | Narrow, app-specific demo hardware (Arducam Mega SPI, Apollo4-only) — likely not worth a direct port. |
| `ns-ipc` | Dropped | none | Decided not to migrate. |
| `ns-model` | Dropped | none | Decided not to migrate. |
| `ns-nnsp` | Dropped | none | Decided not to migrate. |
| `ns-rpc` | Dropped | none | Decided not to migrate; `nsx-nanopb` (protobuf framing) is available as a building block if a transport wrapper is revisited later. |

## Recommended Migration Order

The recommended migration order is:

1. finish hardening the core baseline
2. finish module vendoring, registration, and update workflows
3. migrate broadly useful optional modules next
4. migrate more specialized application stacks only when they provide clear
   reusable value

More concretely, the next module waves should look like this.

### Wave 1: Core Baseline

Focus here first.

1. core runtime and harness behavior
2. profiling and PMU support
3. board, BSP, HAL, startup, and SoC packaging
4. utility cleanup and power behavior
5. clean module management through the NSX CLI

### Wave 2: Useful Optional Modules

These are good follow-on targets once the baseline is stable.

1. USB — done (`nsx-usb`)
2. BLE — done (`nsx-ble`, `nsx-cordio`)
3. RPC or transport helpers — dropped (`ns-rpc`); `nsx-nanopb` remains available as a framing building block if revisited
4. IMU or sensor abstraction — partial (`nsx-sensors`, ICM-45605 only; MPU6050/MAX86150/INA228/LED-stick also live here)
5. audio capture — done (`nsx-audio`)
6. model/runtime integration — dropped (`ns-model`)

These should generally land as optional first-class modules rather than as part
of the starter baseline.

### Wave 3: Specialized Legacy Stacks

These are useful only if they still support real downstream products or demos.

1. camera
2. NNSP-specific stacks
3. narrowly targeted legacy wrappers

The bar here should be higher. If a legacy module is too application-specific
or too tightly coupled to old assumptions, it may be better to redesign it than
to migrate it directly.

## Decision Rules for Future Migrations

Before migrating a legacy module, ask:

1. does it help lightweight bare-metal NSX apps?
2. is it generic enough to serve more than one app or demo?
3. can it be expressed with a smaller and less opinionated API surface?
4. is it better as an optional module than as a baseline dependency?
5. does it fit the NSX module model cleanly?

If the answer is mostly yes, it is a good migration candidate.

## Current Recommendation

NSX is already far enough along to replace the legacy `neuralSPOT` core for:

1. board bring-up
2. smoke tests
3. build, flash, and view workflows
4. common peripheral access
5. profiling and PMU instrumentation

The next phase should not chase broad legacy parity for its own sake.

The next phase should:

1. keep tightening the core replacement
2. migrate the most useful optional modules next
3. use migration as an opportunity to simplify and reduce assumptions in old
   module boundaries

For a lower-level module-by-module tracking view, see the internal coverage page
in [Internal Module Coverage](module-coverage.md).
