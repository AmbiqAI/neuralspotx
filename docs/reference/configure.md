# `nsx configure`

Configures a generated NSX app with CMake.

## Syntax

```text
nsx configure [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
              [--toolchain TOOLCHAIN] [--sdk-root SDK_ROOT]
              [--probe-serial PROBE_SERIAL]
              [--frozen] [--timeout SECONDS] [app]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `app`: optional app name or directory; overrides `--app-dir` and is resolved under the current directory and `examples/`
- `--board`: select a board from the app's supported targets instead of `targets.default`
- `--build-dir`: override build directory
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--sdk-root`: escape hatch — build against an out-of-tree AmbiqSuite root (`NSX_AMBIQSUITE_ROOT_OVERRIDE`) instead of the vendored `nsx-ambiqsuite`; must be a directory, warns that `nsx.lock`/SBOM no longer describe the binary, and cannot be combined with `--frozen`. Omitting it clears a previously cached override. See [SDK provider selection](../user-guide/sdk-provider-selection.md#out-of-tree-sdk-sdk-root)
- `--probe-serial`: select the J-Link probe recorded in generated flash/view targets
- `--frozen`: reject drift between `nsx.yml`, `nsx.lock`, and `modules/` instead of correcting it
- `--timeout`: wall-clock budget per subprocess; a timeout terminates the process group

## Example

```bash
cd <app-dir>
nsx configure
```

## Notes

- `--board` must name a declared supported target
- run `nsx commands --json` for the authoritative machine-readable argument schema
