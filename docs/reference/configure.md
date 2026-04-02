# `nsx configure`

Configures a generated NSX app with CMake.

## Syntax

```text
nsx configure [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`
- `--board`: override board from `nsx.yml`
- `--build-dir`: override build directory

## Example

```bash
nsx configure --app-dir <app-dir>
```

## Notes

- use `--board` only when you explicitly want to override the app metadata
