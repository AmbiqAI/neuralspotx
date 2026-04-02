# `nsx flash`

Builds and flashes a generated NSX app.

## Syntax

```text
nsx flash [--app-dir APP_DIR] [--board BOARD]
          [--build-dir BUILD_DIR] [--jobs JOBS]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override
- `--jobs`: parallel build jobs

## Example

```bash
nsx flash --app-dir <app-dir>
```

## Notes

- requires SEGGER tools in `PATH`
- uses the board-defined flash settings
