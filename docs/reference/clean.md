# `nsx clean`

Removes or resets a generated app build directory.

## Syntax

```text
nsx clean [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
          [--toolchain TOOLCHAIN]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`

## Example

```bash
cd <app-dir>
nsx clean
```
