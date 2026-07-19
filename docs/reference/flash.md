# `nsx flash`

Builds and flashes a generated NSX app.

## Syntax

```text
nsx flash [--app-dir APP_DIR] [--board BOARD]
          [--build-dir BUILD_DIR] [--toolchain TOOLCHAIN]
          [--target TARGET] [--probe-serial SERIAL] [--jobs JOBS]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--target`: optional executable target to flash; omitted selects the app's primary executable
- `--probe-serial`: select one J-Link explicitly when multiple probes are attached
- `--jobs`: parallel build jobs

## Example

```bash
cd <app-dir>
nsx flash

# Flash another executable finalized by the same NSX/CMake project.
nsx flash --target hpx_profiler_power
```

## Notes

- discovers J-Link Commander from `JLINK_PATH`, `PATH`, or the standard
  SEGGER install locations on Linux, macOS, and Windows; the resolved path is
  passed into CMake so discovery is consistent across NSX operations
- uses the board-defined flash settings
- requires the selected target's `.bin` and generated `jlink/<target>/flash_cmds.jlink` recipe
- rejects a successful process exit unless J-Link reports an actual flash-download operation
