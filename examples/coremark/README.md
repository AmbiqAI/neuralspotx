# CoreMark

[EEMBC CoreMark](https://www.eembc.org/coremark/) benchmark for Ambiq Apollo
parts, packaged as a portable **nsx** application.

The example runs the standard `PERFORMANCE_RUN` with `ITERATIONS=0`
(auto-calibrate to ≥10 s), prints the score, and then spins. It uses the
board-default linker script and the SoC's instruction cache — no custom
memory placement or micro-optimization quirks — so the same source builds
unmodified across Apollo5 and Apollo4 targets.

> Energy/power measurement is **not** part of this example. See the separate
> `power_benchmark` example for the Joulescope-based power workflow.

It is a **multi-target** example: a single lean `nsx.yml` declares a
`targets:` block, and the resolved closure for every board is recorded in
one combined `nsx.lock`.

| Target | SoC | Core | Hardware |
|--------|-----|------|----------|
| `apollo510_evb` (default) | Apollo510 | Cortex-M55 | Apollo510 EVB |
| `apollo510b_evb` | Apollo510B | Cortex-M55 | Apollo510B EVB |
| `apollo4p_blue_kxr_evb` | Apollo4P | Cortex-M4 | Apollo4 Blue Plus KXR EVB |

## Build & Run

```bash
# Default board (apollo510_evb)
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires JLink + EVB

# Other targets
nsx build     --app-dir . --board apollo510b_evb
nsx build     --app-dir . --board apollo4p_blue_kxr_evb
```

## Score Output (SEGGER RTT)

The score is printed over **SEGGER RTT** channel 0, not SWO/ITM. RTT writes
to an in-SRAM ring buffer that the J-Link drains over SWD via background
memory reads — no peripheral pins and no sensitivity to clock/baud setup.
On Cortex-M55 targets the port cleans the D-cache after each write so the
host sees fresh bytes; Cortex-M4 targets have no core D-cache and skip it.

Use any RTT viewer (e.g. `JLinkRTTViewer`) to read the output, which looks
like:

```
--- CoreMark on Ambiq NSX ---
2K performance run parameters for coremark.
...
CoreMark 1.0 : <score> / GCC ... / STACK
--- CoreMark complete. ---
```

A minimal scripted capture helper is included:

```bash
python tools/rtt_capture.py --rtt-addr 0x<addr> --duration 25 --out cm.log
```

(`--rtt-addr` is the address of the `_SEGGER_RTT` control block, available
from the linked `coremark` ELF via `nm`/`readelf`.)

## How It Works

1. **Init** (`portable_init`): `nsx_system_init()` brings up the SoC at
   `NSX_PERF_HIGH` with the instruction/data caches enabled, sets up the
   RTT control block, and starts a microsecond timer (`nsx-timer`).
2. **Benchmark** (`core_main`): standard EEMBC CoreMark `PERFORMANCE_RUN`,
   timed with `nsx_timer_us_read()`.
3. **Report** (`portable_fini`): prints the completion banner and spins in
   `__WFI()` so the score stays readable.

## Cleaning Up

Nothing under `build/`, `modules/`, or `.nsx/` is source-controlled —
it is all re-created by `nsx configure`/`nsx build`.

```bash
nsx clean --app-dir .                 # ninja clean inside the active build dir
nsx clean --app-dir . --full          # delete the active build directory
nsx clean --app-dir . --reset         # full reset before `git pull`
nsx clean --app-dir . --reset --force # also discard local edits under modules/
```

## Project Layout

```
coremark/
├── CMakeLists.txt          App build — CoreMark sources + NSX modules
├── nsx.yml                 Lean multi-target manifest (targets + requires)
├── nsx.lock                Combined resolved module locks (targets: map)
├── boards/                 Vendored board definitions (one dir per target)
├── cmake/nsx/              NSX CMake support (toolchains, modules, helpers)
├── modules/                NSX module sources (app-local, gitignored)
├── src/
│   ├── core_portme.c       Portable platform port (init, timer, RTT output)
│   ├── core_portme.h       Port configuration (types, seeds, timer)
│   └── coremark/           Upstream EEMBC CoreMark (Apache-2.0)
└── tools/
    └── rtt_capture.py      Optional scripted RTT score capture (pylink)
```

## License

- Platform port (`src/core_portme.c`, `src/core_portme.h`): Apache-2.0
- EEMBC CoreMark (`src/coremark/`): Apache-2.0
