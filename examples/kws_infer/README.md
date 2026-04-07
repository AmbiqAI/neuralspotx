# kws_infer — Keyword Spotting Inference Example

End-to-end TFLite Micro inference demo on Apollo510, demonstrating:

- **nsx_system** modular init (one-call startup with preset config)
- **nsx_mem** memory placement (tensor arena in TCM, model weights in TCM)
- **NsxPmuProfiler** per-layer PMU profiling via TFLM's MicroProfilerInterface
- **ITM/SWO** printf output at 1 MHz via JLink

## Model

Google Speech Commands KWS (12-class): silence, unknown, yes, no, up, down,
left, right, on, off, stop, go.

- Input: `[1, 49, 10, 1]` int8
- Output: `[1, 12]` int8
- Ops: Conv2D, DepthwiseConv2D, AveragePool2D, FullyConnected, Reshape, Softmax
- Arena: ~20 KB of 64 KB allocated
- Inference: ~21 ms @ 192 MHz HP mode with I/D cache

## Build

```bash
cd neuralspotx/examples/kws_infer
cmake -S . -B build/apollo510_evb -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/nsx/toolchains/arm-none-eabi-gcc.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DNSX_BOARD=apollo510_evb
cmake --build build/apollo510_evb
```

## Flash & View Output

```bash
JFlashLiteExe -device AP510NFA-CBR -if SWD -speed 4000 \
  build/apollo510_evb/kws_infer.bin -addr 0x00410000

JLinkSWOViewerCLExe -device AP510NFA-CBR -itmport 0 -swofreq 1000000
```

## System Init

Uses `nsx_system_init()` with a modified development preset:

```c
nsx_system_config_t cfg = nsx_system_development;
cfg.skip_bsp_init = true;   // skip BSP's 2-second delay
nsx_system_init(&cfg);       // → core, CPDLP, cache, HP mode, SpotMgr, ITM
```

This replaces ~60 lines of manual DCU/TPIU/ITM/cache/SpotManager init.

## Key Files

| File | Purpose |
|------|---------|
| `src/main.cc` | Application entry — system init, TFLM setup, inference loop |
| `src/kws_model_data.h` | Model weights as C array (in TCM via default .data) |
| `src/nsx_pmu_profiler.h` | Per-layer PMU profiler (TFLM MicroProfilerInterface) |
| `src/nsx_pmu_profiler.cc` | PMU profiler implementation — cycles, dcache misses, icache misses |
| `CMakeLists.txt` | Build config — links HeliaRT v1.7.0 prebuilt + NSX modules |

## Dependencies

- ARM GCC 14.3 (`arm-none-eabi-gcc`)
- HeliaRT v1.7.0 (`release-with-logs` variant, for profiler hooks)
- NSX modules: `nsx-core`, `nsx-power`, `nsx-pmu-armv8m`, `nsx-harness`
