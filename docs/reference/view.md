# `nsx view`

Opens the SEGGER SWO viewer for a generated NSX app.

## Syntax

```text
nsx view [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: build directory override

## Example

```bash
cd <nsx-repo>
uv run nsx view --app-dir <app-dir>
```

## Notes

- requires SEGGER SWO tooling in `PATH`
- depends on the target being configured for SWO output
