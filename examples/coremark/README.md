# CoreMark

[EEMBC CoreMark](https://www.eembc.org/coremark/) benchmark for
Apollo510 EVB, optimized for both peak score and power measurement.

The benchmark runs from **ITCM** (zero-wait-state SRAM) via a custom
linker script.  After printing the score over SWO, the firmware enters
an aggressive power-down sequence and loops CoreMark indefinitely from
ITCM with NVM, caches, and all unused peripherals off — ready for
power capture with a Joulescope or similar tool.

## Quick Start

```bash
nsx configure --app-dir .
nsx build --app-dir .
nsx flash --app-dir .
nsx view --app-dir .          # opens SWO viewer, prints CoreMark score
```

## Build Options

Pass CMake options via `-D` flags during `nsx configure`:

| Option | Default | Description |
|--------|---------|-------------|
| `COREMARK_HP_MODE` | `OFF` | Run at HP 250 MHz instead of LP 96 MHz |
| `COREMARK_SCORE_ONLY` | `OFF` | Print score and halt — skip the power measurement loop |
| `USE_ARMCLANG_COREMARK` | `OFF` | Compile CoreMark hot-path with armclang `-Ofast` (requires Arm Compiler 6) |

Examples:

```bash
# High-performance mode (250 MHz)
nsx configure --app-dir . -- -DCOREMARK_HP_MODE=ON

# Score only, no power loop
nsx configure --app-dir . -- -DCOREMARK_SCORE_ONLY=ON

# Mixed toolchain: armclang for CoreMark, GCC for everything else
nsx configure --app-dir . -- -DUSE_ARMCLANG_COREMARK=ON
```

## How It Works

1. **Init** (`portable_init`): Full SoC init via `nsx_system_init()`, selects
   LP or HP clock mode, configures power-monitor GPIOs, starts microsecond
   timer.

2. **Benchmark** (`core_main`): Standard EEMBC CoreMark PERFORMANCE_RUN with
   `ITERATIONS=0` (auto-calibrate to ≥10 s). Score printed over SWO.

3. **Power measurement** (`portable_fini` → `itcm_power_loop`):
   - Disables SWO/ITM
   - Applies aggressive `ns_power_config` (all peripherals off, LP mode)
   - Kills all device peripherals, stops all timers
   - Reduces memory to 32K ITCM + 128K DTCM, single NVM bank, no SSRAM
   - Tristates all GPIOs except the two Joulescope monitor pins
   - Jumps to `itcm_power_loop()` (in `.itcm_text` section):
     - Powers off NVM (MRAM)
     - Disables I-cache and D-cache
     - Sets GPIO phase = ACTIVE
     - Runs `iterate()` forever from ITCM

## Power Measurement with Joulescope

### Hardware Setup

1. Connect Joulescope JS220 (or JS110) in series with the Apollo510 EVB
   power supply.
2. Connect two GPIO fly-wires from the EVB to the Joulescope GPI header:
   - **GPIO 29** → GPI bit 0 (IN0)
   - **GPIO 30** → GPI bit 1 (IN1)

These GPIOs signal the measurement phase using the
`ns_set_power_monitor_state()` protocol:

| GPI Value | Phase | Description |
|-----------|-------|-------------|
| `0b00` | IDLE/Sleep | System idle or deep-sleep |
| `0b01` | ACTIVE | CoreMark compute running |
| `0b11` | SIGNAL | Start/stop marker |

### Capture Script

A helper script is included in `tools/`:

```bash
pip install joulescope
python tools/joulescope_capture.py
```

Options:

```
--duration N     Capture for N seconds (0 = until Ctrl-C)
--io-voltage V   GPIO voltage level: 1.8V (default) or 3.3V
--reduction-freq Set statistics reduction frequency (default: "50 Hz")
```

The script watches GPIO transitions, accumulates per-phase power
statistics, and prints a summary:

```
======================================================================
CAPTURE SUMMARY
======================================================================
  ACTIVE      : I=   2.461 mA  V= 1.800 V  P=   4.430 mW  t=   30.0 s
  SLEEP       : I=   0.003 mA  V= 1.800 V  P=   0.005 mW  t=   30.0 s

  CoreMark/mW = CoreMark_score / 4.430 mW
======================================================================
```

### Manual Measurement

If not using the capture script, flash the board and wait for the SWO
score output.  Once the firmware enters the power loop, the ACTIVE GPIO
goes high and stays high — measure steady-state current with any tool.

## Project Layout

```
coremark/
├── CMakeLists.txt          App build — CoreMark sources + NSX modules
├── nsx.yml                 NSX project manifest (board, modules, toolchain)
├── linker_script_itcm.ld   Custom LD: CoreMark hot-path in ITCM
├── boards/                 Vendored board definition (apollo510_evb)
├── cmake/nsx/              NSX CMake support (toolchains, modules, helpers)
├── modules/                NSX module sources (app-local, gitignored)
├── src/
│   ├── core_portme.c       Platform port (init, timer, power-down, GPIO)
│   ├── core_portme.h       Port configuration (types, seeds, timer)
│   └── coremark/           Upstream EEMBC CoreMark (Apache-2.0)
└── tools/
    └── joulescope_capture.py  Automated Joulescope power capture
```

## License

- Platform port (`src/core_portme.c`, `src/core_portme.h`): Apache-2.0
- EEMBC CoreMark (`src/coremark/`): Apache-2.0
