# Power Benchmark

Three power benchmarks for Apollo510 EVB in a single example:

| Mode | What it measures | Active workload |
|------|-----------------|----------------|
| `coremark` | Active compute efficiency | EEMBC CoreMark from ITCM, NVM off |
| `while1` | Minimum active current | Tight NOP loop from ITCM, NVM off |
| `deepsleep` | Sleep floor | WFI deep sleep, all peripherals off |

All modes use GPIO instrumentation for automated Joulescope capture.

## Quick Start

```bash
# Build (default: coremark, LP 96 MHz, GCC)
nsx build --app-dir .

# Flash
nsx flash --app-dir .

# Capture power (60 seconds, auto-detects active/sleep phases via GPIO)
python tools/joulescope_capture.py --duration 60
```

## Build Options

| CMake Variable | Values | Default | Description |
|---|---|---|---|
| `BENCHMARK_MODE` | `coremark`, `while1`, `deepsleep` | `coremark` | Benchmark workload |
| `BENCHMARK_HP_MODE` | `ON`/`OFF` | `OFF` | HP 250 MHz (ON) or LP 96 MHz (OFF) |
| `USE_ARMCLANG` | `ON`/`OFF` | `OFF` | Compile CoreMark with armclang -Ofast |

```bash
# While(1) at LP 96 MHz
nsx configure --app-dir .
cmake build/apollo510_evb -DBENCHMARK_MODE=while1
cmake --build build/apollo510_evb --clean-first

# Deep sleep
cmake build/apollo510_evb -DBENCHMARK_MODE=deepsleep
cmake --build build/apollo510_evb --clean-first

# CoreMark HP 250 MHz with armclang
cmake build/apollo510_evb -DBENCHMARK_MODE=coremark -DBENCHMARK_HP_MODE=ON -DUSE_ARMCLANG=ON
cmake --build build/apollo510_evb --clean-first
```

## Power-Down Sequence

The example demonstrates the correct sequencing for minimum power
using `nsx-power` module helpers (no raw register writes):

```
1. ns_power_disable_debug()         — SWO/ITM off
2. ns_power_shutdown_peripherals()  — all peripherals + timers off
3. ns_power_minimize_memory()       — 32K ITCM + 128K DTCM, no SSRAM
4. ns_power_tristate_gpios()        — float unused pins
5. ns_set_performance_mode()        — select LP or HP clock LAST
6. ns_power_disable_nvm()           — request NVM (MRAM) power-off
7. NS_POWER_DRAIN_NVM()             — force bus cycle to finalize
8. ns_power_disable_caches()        — I/D cache off (while1 only)
```

Steps 1–5 execute from MRAM. Steps 6–8 execute from the ITCM
trampoline (a small function placed in zero-wait-state ITCM whose
job is to shut down NVM and then run the benchmark forever — the
CPU can’t power off MRAM while still fetching instructions from it).
For deep sleep mode, steps 6–8 are skipped (NVM stays on for the
wakeup path).

## Measurement Setup

- **Toolchains**: GCC 14.3.1 (`-O3`), armclang 6.24 (`-Ofast -mcpu=cortex-m55`)
- **Board**: Apollo510 EVB (AP510NFA-CBR)
- **Power monitor**: Joulescope JS110 on VDDCML rail
- **SWO**: JLink SWO Viewer at 96 MHz trace clock (`nsx view --app-dir .`)

**What is shut down during measurement:**

- All peripheral power domains (USB, audio, crypto, IOM, etc.)
- All 16 hardware timers, XTAL oscillator, voltage comparator
- Shared SRAM (3 MB off), TCM reduced to 32 KB ITCM + 128 KB DTCM
- NVM (MRAM) powered off for active modes (while1, coremark)
- I/D cache disabled for while1 (CoreMark keeps I-cache for libc calls)
- All GPIOs tristated except the two Joulescope phase-detection pins
- SWO/ITM debug output and debug power domain

CoreMark hot-path objects are placed in zero-wait-state ITCM via the
linker script so that MRAM can be fully powered off during the run.

## GPIO Phase Detection

Two GPIOs signal the current phase to the Joulescope capture script:

| GPIO29 | GPIO36 | Phase |
|--------|--------|-------|
| LOW | LOW | IDLE (boot / deep sleep) |
| HIGH | LOW | ACTIVE (benchmark running) |
