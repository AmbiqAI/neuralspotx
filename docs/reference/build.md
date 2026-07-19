# `nsx build`

Builds a generated NSX app.

## Syntax

```text
nsx build [--app-dir APP_DIR] [--board BOARD]
          [--build-dir BUILD_DIR] [--toolchain TOOLCHAIN]
          [--target TARGET] [--jobs JOBS] [--update] [--frozen]
          [--timeout SECONDS] [app]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `app`: optional app name or directory; overrides `--app-dir` and is resolved under the current directory and `examples/`
- `--board`: select a board from the app's supported targets instead of `targets.default`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--target`: explicit build target
- `--jobs`: parallel build jobs
- `--update`: re-resolve module constraints to upstream tips and re-vendor before building
- `--frozen`: when configure is needed, reject manifest, lock, or vendored-module drift
- `--timeout`: wall-clock budget per subprocess; a timeout terminates the process group

## Example

```bash
cd <app-dir>
nsx build --jobs 8
```

## Notes

- this operates on the generated app’s CMake build tree
- run `nsx commands --json` for the authoritative machine-readable argument schema
