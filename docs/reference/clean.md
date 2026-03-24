# `nsx clean`

Removes or resets a generated app build directory.

## Syntax

```text
nsx clean [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override

## Example

```bash
cd <nsx-repo>
uv run nsx clean --app-dir <app-dir>
```
