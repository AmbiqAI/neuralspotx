# neuralspotx Examples

Self-contained example applications that showcase different nsx-module
combinations.  Each directory is a complete **nsx app** – it has an
`nsx.yml`, a `CMakeLists.txt`, and a `src/main.c`.

## Quick start

```bash
cd examples/hello_world          # pick an example
nsx configure --app-dir .        # fetch modules + run CMake
nsx build     --app-dir .        # compile
nsx flash     --app-dir .        # (optional) flash to EVB
nsx view      --app-dir .        # (optional) SWO viewer
```

## Examples

| Directory        | Extra modules      | What it shows                           |
|------------------|--------------------|-----------------------------------------|
| `hello_world`    | *(base only)*      | Minimal app – SWO printf loop           |
| `power_benchmark`| `nsx-power`        | Power measurement: CoreMark, while(1), deep sleep |
| `coremark`       | `nsx-power`        | EEMBC CoreMark with ITCM + NVM shutdown |
| `kws_infer`      | `cmsis-nn`         | Keyword-spotting TFLite Micro inference  |
| `pmu_profiling`  | `nsx-pmu-armv8m`   | PMU cycle / event counting              |
| `audio_capture`  | `nsx-audio`        | PDM microphone capture + SWO stats      |
| `usb_serial`     | `nsx-usb`          | USB CDC echo                            |
| `usb_rpc`        | `nsx-usb`, `nsx-nanopb` | USB RPC with protobuf serialization |

All examples target the **Apollo510 EVB** (`apollo510_evb` profile).

## Running the E2E test suite

From the repo root:

```bash
cd neuralspotx
pytest tests/test_example_builds.py -v
```

Requires `arm-none-eabi-gcc`, `cmake`, and `ninja` on PATH.  Tests that
cannot find the toolchain are skipped automatically.
