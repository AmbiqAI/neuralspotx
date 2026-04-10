# `nsx build`

Builds a generated NSX app.

## Syntax

```text
nsx build [--app-dir APP_DIR] [--board BOARD]
          [--build-dir BUILD_DIR] [--toolchain TOOLCHAIN]
          [--target TARGET] [--jobs JOBS]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--target`: explicit build target
- `--jobs`: parallel build jobs

## Example

```bash
nsx build --app-dir <app-dir> --jobs 8
```

## Notes

- this operates on the generated app’s CMake build tree
