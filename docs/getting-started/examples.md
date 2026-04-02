# Examples

Ready-to-build example apps live in the
[`examples/`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples)
directory of the neuralspotx repository.  Each one is a self-contained nsx
app — clone the repo and you can configure, build, and flash straight away.

## Available examples

| Directory | Extra modules | What it shows |
|---|---|---|
| [`hello_world`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/hello_world) | *(base profile only)* | Minimal app — SWO printf loop |
| [`pmu_profiling`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/pmu_profiling) | `nsx-pmu-armv8m` | PMU cycle / event counting |
| [`audio_capture`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/audio_capture) | `nsx-audio` | PDM microphone capture + SWO stats |
| [`usb_serial`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/usb_serial) | `nsx-usb` | USB CDC echo |

All examples target the **Apollo510 EVB** (`apollo510_evb` profile).

## Quick start

```bash
git clone https://github.com/AmbiqAI/neuralspotx.git
cd neuralspotx/examples/hello_world

nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .   # optional — requires an EVB
nsx view      --app-dir .   # optional — SWO viewer
```

`nsx configure` automatically clones any missing registry modules, so
there is no separate module-install step.

## Trying a different example

Just change the directory:

```bash
cd ../pmu_profiling
nsx configure --app-dir .
nsx build     --app-dir .
```

## Structure of each example

```
<example>/
├── nsx.yml          # module list and board target
├── CMakeLists.txt   # CMake entry point
├── src/
│   └── main.c
└── README.md
```

Vendored modules (`modules/`) and the build directory are gitignored and
re-created automatically by `nsx configure`.
