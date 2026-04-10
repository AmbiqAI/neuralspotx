# `nsx view`

Opens the SEGGER SWO viewer for a generated NSX app.

By default, `nsx view` starts the viewer first and then runs the app's normal
SEGGER reset target once. This avoids a common race where SWO stays empty if
the target is already running before the viewer is listening.

## Syntax

```text
nsx view [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
         [--toolchain TOOLCHAIN] [--no-reset-on-open] [--reset-delay-ms RESET_DELAY_MS]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--no-reset-on-open`: open the viewer without issuing the normal reset target after attach
- `--reset-delay-ms`: wait time before issuing the reset target after the viewer opens

## Example

```bash
nsx view --app-dir <app-dir>
```

## Notes

- requires SEGGER SWO tooling in `PATH`
- depends on the target being configured for SWO output
- uses the board's normal SEGGER `Reset` flow by default; it does not require a stronger reset mode for Apollo510
