# Internal Module Coverage

For the higher-level migration plan and module matrix, see
[Migrating from neuralSPOT](migration-from-neuralspot.md).

This page tracks how the major internal `neuralSPOT` module areas map into the
current NSX module set.

## Historical mapping (neuralSPOT → nsx)

These tables document how the major neuralSPOT internal areas map
into the current NSX module set. They are retrospective — the goal
is not to preserve every neuralSPOT package name, but to make sure
the important internal capabilities have a clear home in NSX.

### Covered baseline areas

These major internal areas already have clear NSX coverage.

| neuralSPOT area | Current NSX coverage | Notes |
| --- | --- | --- |
| `ns-core` | `nsx-core` | Core runtime init and common bring-up surface are migrated. |
| `ns-harness` | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m` | Print/debug/interrupt shims now live in `nsx-core`; perf/PMU-based profiling moved into `nsx-perf`/`nsx-pmu-armv8m`. TFLM `DebugLog` registration is superseded by `helia-rt`'s own implementation. |
| `ns-utils` | `nsx-core`, `nsx-perf`, `nsx-pmu-armv8m`, `nsx-power` | Timer, malloc, portable printf/delay/interrupt, and energy-adjacent helpers are distributed across these focused modules rather than a single `nsx-utils`. |
| `ns_perf_profile` | `nsx-perf` | Generic DWT/cache/PC-sampling performance capture is split into its own module. |
| `ns_pmu_*` | `nsx-pmu-armv8m` | Arm PMU configuration, presets, and accumulation are split into a dedicated module. |
| `ns-peripherals` generic helpers | `nsx-power`, `nsx-psram`, board button facts on `nsx-gpio` | Legacy mixed helpers were retired into focused unified surfaces instead of a single replacement module. |
| `ns-power` | `nsx-power` | Power policy, block shutdown, retention, and sleep helpers are present as a first-class module. |
| `ns-uart` | `nsx-uart` | Optional UART wrapper migrated with current shim dependencies. |
| `ns-i2c` | `nsx-i2c`, `nsx-sensors` | Bus wrapper/register-driver helpers are in `nsx-i2c`; sample I2C device drivers (MPU6050, MAX86150) moved into `nsx-sensors`. |
| `ns-spi` | `nsx-spi` | Optional SPI wrapper migrated with current shim dependencies. |
| `ns-audio` | `nsx-audio` | PDM audio capture driver with DMA-backed sampling and callback delivery. |
| `ns-usb` | `nsx-usb` | USB CDC serial driver using TinyUSB with proper error handling. |
| `ns-nanopb` | `nsx-nanopb` | Vendored nanopb — zero-dynamic-memory Protocol Buffers in ANSI C. |
| `ns-ble` | `nsx-ble`, `nsx-cordio` | First-class, registry-listed. Hardware-smoke validated via the `ble_webble` example; still an early baseline (single service/connection, no OOB pairing). |
| `ns-imu` (ICM-45605 only) | `nsx-sensors` | TDK "basic driver" scope ported; the rest of the legacy generic `ns-imu` wrapper was intentionally not carried forward. |
| `ns-physiokit` (separate repo) | `nsx-physiokit` | First-class, registry-listed. Biosignal (ECG/PPG/respiration/HRV) primitives, built on `helia-dsp`. |
| `ns-tileio` (separate repo) | `nsx-tileio-ble`, `nsx-tileio-usb` | First-class, registry-listed. Hardware validated on Apollo4 Blue Plus and Apollo510B. |
| Ambiq HAL/BSP wiring | `nsx-ambiq-hal`, `nsx-ambiq-bsp`, `nsx-soc-hal`, `nsx-cmsis-startup` | Split into SDK-facing wrappers plus SoC/startup integration. |
| thin common wrappers | `nsx-core` | The legacy migration shim is now absorbed into `nsx-core`, which exports printf, delay, and interrupt helpers directly. |

## Partially covered areas

These areas have some coverage, but the full neuralSPOT feature surface is not yet
represented as first-class NSX modules.

| neuralSPOT area | Current state | Notes |
| --- | --- | --- |
| `ns-peripherals` extended features | partial | PSRAM, NVM, and some SoC-specific peripheral pieces still need tighter normalization. |
| migrated bus modules | partial | The wrappers are present, but deeper API cleanup and hardware-assumption trimming are still future work. |
| TFLM per-layer profiler glue (`ns-harness`'s `MicroProfiler`) | partial | Functionally migrated as `NsxPmuProfiler`, built on `nsx-pmu-armv8m`, but it still only lives as example-local source in `kws_infer` rather than a reusable module. |
| print and low-power print behavior | partial | Basic print paths exist; deeper legacy power-aware print behavior is not fully split out yet. |

## Major neuralSPOT areas still missing

These remain valid migration targets if they still matter for NSX.

| neuralSPOT area | Likely NSX direction |
| --- | --- |
| `ns-camera` | optional camera/sensor module; narrow, app-specific demo hardware — likely not worth a direct port |
| `ns-features` | optional DSP/features module (legacy `ns-features` exists but not yet fully on `nsx-module.yaml`) |
| `ns-ipc` | dropped — decided not to migrate |
| `ns-model` | dropped — decided not to migrate |
| `ns-nnsp` | dropped — decided not to migrate |
| `ns-rpc` | dropped — decided not to migrate; `nsx-nanopb` remains available as a framing building block if revisited |

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

1. broaden BLE app coverage and promote `nsx-cordio`/`nsx-ble` past their early
   baseline status
2. package the TFLM per-layer profiler glue (`NsxPmuProfiler`) as a reusable
   module instead of example-local source
3. revisit `ns-features` if a concrete app need surfaces
