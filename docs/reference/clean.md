# `nsx clean`

Removes or resets a generated app build directory.

## Syntax

```text
nsx clean [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
          [--toolchain TOOLCHAIN]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`

## Example

```bash
nsx clean --app-dir <app-dir>
```
