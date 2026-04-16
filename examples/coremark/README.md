# CoreMark

EEMBC CoreMark benchmark for Apollo510 EVB.

Runs the standard CoreMark benchmark with configurable execution modes
(ITCM, NVM) and clock speeds (LP 96 MHz, HP 250 MHz). Results are
output via SWO.

## Build

```bash
nsx configure --app-dir .
nsx build --app-dir .
nsx flash --app-dir .
nsx view --app-dir .
```

## Layout

- `cmake/nsx/` — NSX CMake support
- `modules/` — NSX module sources (app-local)
- `boards/` — Vendored board definition
- `src/` — CoreMark source and port files
