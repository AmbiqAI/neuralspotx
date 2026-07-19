# neuralspotx Examples

Self-contained applications that showcase NSX workflows and module
combinations. Each directory is a complete **NSX app** with its own `nsx.yml`,
`nsx.lock`, `CMakeLists.txt`, sources, and usage notes. This file is the
canonical repository catalog for contributors and source-checkout users.

## Quick start

```bash
cd examples/hello_world          # pick an example
nsx configure --app-dir .        # fetch modules + run CMake
nsx build     --app-dir .        # compile
nsx flash     --app-dir .        # (optional) flash to EVB
nsx view      --app-dir .        # (optional) SWO viewer
```

## Examples

| Directory | Modules declared by the app | What it shows |
|---|---|---|
| `hello_world` | *(board profile only)* | Minimal SWO printf loop and multi-target build |
| `freertos_blinky` | `nsx-freertos` | Application-owned FreeRTOS configuration on Cortex-M4F/M55 |
| `coremark` | `nsx-interrupt`, `nsx-timer` | EEMBC CoreMark with ITCM execution and NVM shutdown |
| `power_benchmark` | `nsx-power`, `nsx-gpio`, `nsx-timer`, `nsx-interrupt` | Three-phase power measurement firmware |
| `pmu_profiling` | `nsx-pmu-armv8m` | PMU cycle and event counting |
| `kws_infer` | `nsx-power`, `nsx-pmu-armv8m`, `nsx-helia-rt` | Keyword-spotting TFLite Micro inference |
| `audio_capture` | `nsx-audio` | PDM microphone capture and SWO statistics |
| `ble_webble` | `nsx-freertos`, `nsx-cordio`, `nsx-ble` | Bluetooth LE peripheral with app-owned stack policy |
| `usb_serial` | `nsx-ambiq-usb`, `nsx-usb`, `nsx-timer`, `nsx-interrupt` | USB CDC echo |
| `usb_rpc` | `nsx-usb`, `nsx-nanopb` | USB RPC with protobuf serialization |

Most examples default to the **Apollo510 EVB** (`apollo510_evb`). Each
manifest's `targets.default` and `targets.supported` fields are the source of
truth for its current board coverage; `ble_webble` defaults to
`apollo4p_blue_kxr_evb`.

To try one example without cloning the repository, download the repository
archive and extract the desired directory:

```bash
curl -fL https://github.com/AmbiqAI/neuralspotx/archive/refs/heads/main.tar.gz \
  | tar -xz -f - --strip-components=2 neuralspotx-main/examples/hello_world
cd hello_world
nsx configure
nsx build
```

## Running the E2E test suite

From the repo root:

```bash
cd neuralspotx
pytest tests/test_example_builds.py -v
```

Requires `arm-none-eabi-gcc`, `cmake`, and `ninja` on PATH.  Tests that
cannot find the toolchain are skipped automatically.
