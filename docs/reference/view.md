# `nsx view`

Opens the SEGGER SWO viewer for a generated NSX app.

By default, `nsx view` chooses the board-appropriate reset policy. Most boards
start the viewer first and then run the app's normal SEGGER reset target once.
Apollo4 secure boards attach without resetting because SEGGER's Apollo4 reset
flow halts in the secure boot handoff and can make the SWO viewer exit.

## Syntax

```text
nsx view [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
         [--toolchain TOOLCHAIN] [--sdk-root SDK_ROOT]
         [--probe-serial PROBE_SERIAL] [--frozen]
         [--reset-on-open | --no-reset-on-open]
         [--reset-delay-ms RESET_DELAY_MS] [--duration SECONDS]
         [--capture FILE] [--timeout SECONDS] [app]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `app`: optional app name or directory; overrides `--app-dir` and is resolved under the current directory and `examples/`
- `--board`: select a board from the app's supported targets instead of `targets.default`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--sdk-root`: escape hatch — when a configure is needed, build against an out-of-tree AmbiqSuite root (`NSX_AMBIQSUITE_ROOT_OVERRIDE`); warns that `nsx.lock`/SBOM no longer describe the binary and cannot be combined with `--frozen`. See [SDK provider selection](../user-guide/sdk-provider-selection.md#out-of-tree-sdk-sdk-root)
- `--probe-serial`: select a specific J-Link probe
- `--frozen`: when configure is needed, reject manifest, lock, or vendored-module drift; explicit probe selection still forces configure
- `--reset-on-open`: force a reset after opening the viewer
- `--no-reset-on-open`: open the viewer without issuing the normal reset target after attach
- `--reset-delay-ms`: wait time before issuing the reset target after the viewer opens
- `--duration`: stop the viewer after the given number of seconds
- `--capture`: stream SWO output to a file as well as standard output
- `--timeout`: wall-clock budget per subprocess; a timeout terminates the process group

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
- run `nsx commands --json` for the authoritative machine-readable argument schema
