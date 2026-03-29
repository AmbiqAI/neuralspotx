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
2. `nsx-harness`
3. `nsx-utils`
4. `nsx-perf`
5. `nsx-pmu-armv8m`
6. `nsx-peripherals`
7. `nsx-power`
8. `nsx-i2c`
9. `nsx-spi`
10. `nsx-uart`
11. `nsx-soc-hal`
12. `nsx-cmsis-startup`
13. `nsx-ambiq-hal-r*`
14. `nsx-ambiq-bsp-r*`

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
3. platform SDK consumption is split across provider, HAL, BSP, startup, and
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
| `ns-harness` | Migrated | `nsx-harness` | Print, debug, and profiling-adjacent harness support are present. |
| `ns-i2c` | Migrated | `nsx-i2c` | Bus wrapper and register-driver helpers are available. |
| `ns-spi` | Migrated | `nsx-spi` | SPI wrapper support is available. |
| `ns-uart` | Migrated | `nsx-uart` | UART wrapper support is available. |
| `ns-features` | Migrated | `ns-features` | The legacy features area already has a direct module home. |
| `ns-peripherals` | Split | `nsx-peripherals`, `nsx-power` | Generic peripherals and power policy were separated into clearer modules. |
| `ns-utils` | Split | `nsx-utils`, `nsx-perf`, `nsx-pmu-armv8m`, `nsx-power` | Legacy utilities bundled several concerns that are now being separated. |
| `ns-ble` | Partial | no first-class `nsx-ble` yet | BLE-related code exists in add-on areas, but not as a clean first-class NSX module. |
| `ns-usb` | Partial | no first-class `nsx-usb` yet | USB transport pieces exist in add-on form, but not as a standalone NSX module. |
| `ns-imu` | Partial | sensor and physiokit modules | Pieces exist, but there is not yet a broad migration-equivalent IMU module. |
| `ns-audio` | Future | none yet | Candidate optional module if audio capture remains important. |
| `ns-camera` | Future | none yet | Candidate optional camera or sensor module. |
| `ns-ipc` | Future | none yet | Candidate utility module if ring-buffer or IPC patterns remain broadly useful. |
| `ns-model` | Future | none yet | Candidate model/runtime integration module once the baseline is stable. |
| `ns-nnsp` | Future | none yet | Candidate optional signal or speech-processing module rather than baseline. |
| `ns-rpc` | Future | none yet | Candidate optional transport or RPC module. |

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

1. USB
2. BLE
3. RPC or transport helpers
4. IMU or sensor abstraction
5. audio capture
6. model/runtime integration

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
3. use migration as an opportunity to simplify and de-opinionate old module
   boundaries

For a lower-level module-by-module tracking view, see the internal coverage page
in [Internal Module Coverage](../contributing/module-coverage.md).
