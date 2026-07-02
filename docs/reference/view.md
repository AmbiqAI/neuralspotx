# `nsx view`

Opens the SEGGER SWO viewer for a generated NSX app.

By default, `nsx view` chooses the board-appropriate reset policy. Most boards
start the viewer first and then run the app's normal SEGGER reset target once.
Apollo4 secure boards attach without resetting because SEGGER's Apollo4 reset
flow halts in the secure boot handoff and can make the SWO viewer exit.

## Syntax

```text
nsx view [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
         [--toolchain TOOLCHAIN] [--reset-on-open | --no-reset-on-open]
         [--reset-delay-ms RESET_DELAY_MS]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--reset-on-open`: force a reset after opening the viewer
- `--no-reset-on-open`: open the viewer without issuing the normal reset target after attach
- `--reset-delay-ms`: wait time before issuing the reset target after the viewer opens

## Example

```bash
cd <app-dir>
nsx view
```

## Notes

- requires SEGGER SWO tooling in `PATH`
- depends on the target being configured for SWO output
- Apollo4 secure boards are validated with `nsx flash` followed by attach-only `nsx view`
- Apollo510 keeps the normal viewer-first `Reset` flow; it does not require a stronger reset mode
