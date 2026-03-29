# Internal Module Coverage

For the higher-level migration plan and module matrix, see
[Migrating from neuralSPOT](../architecture/migration-from-neuralspot.md).

This page tracks how the major internal `neuralSPOT` module areas map into the
current NSX module set.

The goal is not to preserve every legacy package name. The goal is to make sure
the important internal capabilities have a clear home in NSX.

## Covered Baseline Areas

These major internal areas already have clear NSX coverage.

| Legacy area | Current NSX coverage | Notes |
| --- | --- | --- |
| `ns-core` | `nsx-core` | Core runtime init and common bring-up surface are migrated. |
| `ns-harness` | `nsx-harness` | Print, debug-log bridge, and micro-profiler support are present. |
| `ns-utils` | `nsx-utils` | Timer, malloc, and energy helpers are present. |
| `ns_perf_profile` | `nsx-perf` | Generic DWT/cache/PC-sampling performance capture is split into its own module. |
| `ns_pmu_*` | `nsx-pmu-armv8m` | Arm PMU configuration, presets, and accumulation are split into a dedicated module. |
| `ns-peripherals` generic helpers | `nsx-peripherals` | Button, PSRAM, and NVM support are present. |
| `ns-power` | `nsx-power` | Power policy, block shutdown, retention, and sleep helpers are present as a first-class module. |
| `ns-uart` | `nsx-uart` | Optional UART wrapper migrated with current shim dependencies. |
| `ns-i2c` | `nsx-i2c` | Optional I2C wrapper and register-driver helpers are migrated. |
| `ns-spi` | `nsx-spi` | Optional SPI wrapper migrated with current shim dependencies. |
| Ambiq HAL/BSP wiring | `nsx-ambiq-hal-r*`, `nsx-ambiq-bsp-r*`, `nsx-soc-hal`, `nsx-cmsis-startup` | Split into SDK-facing wrappers plus SoC/startup integration. |
| thin common wrappers | `nsx-portable-api` | Optional migration-friendly shim for printf, delay, and interrupt helpers. |

## Partially Covered Areas

These areas have some coverage, but the full legacy feature surface is not yet
represented as first-class NSX modules.

| Legacy area | Current state | Notes |
| --- | --- | --- |
| `ns-peripherals` extended features | partial | PSRAM, NVM, and some SoC-specific peripheral pieces still need tighter normalization. |
| migrated bus modules | partial | The wrappers are present, but deeper API cleanup and hardware-assumption trimming are still future work. |
| profiling helpers spread across `ns-utils` and `ns-harness` | partial | Generic perf and PMU helpers now have dedicated modules; legacy TFLM-oriented profiling glue remains in `nsx-harness`. |
| print and low-power print behavior | partial | Basic print paths exist; deeper legacy power-aware print behavior is not fully split out yet. |

## Major Legacy Areas Still Missing

These remain valid migration targets if they still matter for NSX.

| Legacy area | Likely NSX direction |
| --- | --- |
| `ns-audio` | optional audio/input module set |
| `ns-ble` | optional connectivity module |
| `ns-camera` | optional camera/sensor module |
| `ns-features` | optional DSP/features module |
| `ns-imu` | optional sensor driver/module |
| `ns-ipc` | optional IPC/ring-buffer utility module |
| `ns-model` | optional model/runtime integration module |
| `ns-nnsp` | optional neural signal/audio processing module |
| `ns-rpc` | optional RPC/transport module |
| `ns-usb` | optional USB module set |

## Migration Guidance

When deciding whether to migrate a legacy internal module, use this test:

1. Is it useful for lightweight bare-metal NSX apps?
2. Is it better as an optional module than as part of the baseline starter set?
3. Does it provide stable value beyond direct AmbiqSuite calls?
4. Is it generic enough to support more than one smoke/demo app?

If the answer is mostly yes, it is a good NSX module candidate.

## Current Recommendation

The baseline internal module coverage is good enough for:

- app creation
- build/flash/view workflows
- core bring-up
- simple profiling-oriented apps
- migration-friendly helper shims

The next migration priority should focus on optional app-facing stacks, not on
reworking the existing baseline:

1. connectivity modules such as USB and future RPC replacements
2. audio/model/features modules used by lightweight AI demos
3. sensor-oriented modules such as IMU and camera
