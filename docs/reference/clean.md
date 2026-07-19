# `nsx clean`

Removes or resets a generated app build directory.

## Syntax

```text
nsx clean [--app-dir APP_DIR] [--board BOARD] [--build-dir BUILD_DIR]
          [--toolchain TOOLCHAIN] [--full] [--reset] [--force]
          [--timeout SECONDS] [app]
```

## Main Arguments

- `--app-dir`: app directory containing `nsx.yml`; when omitted, NSX searches upward from the current directory
- `app`: optional app name or directory; overrides `--app-dir` and is resolved under the current directory and `examples/`
- `--board`: select a board from the app's supported targets instead of `targets.default`
- `--build-dir`: build directory override
- `--toolchain`: toolchain override (`gcc`, `armclang`, `atfe`). Defaults to `nsx.yml` → `arm-none-eabi-gcc`
- `--full`: remove the full selected build directory instead of running the build-system clean target
- `--reset`: remove all `build*/` directories, the synced `modules/` tree, and `.nsx/` to restore freshly cloned app state
- `--force`: with `--reset`, discard locally modified files under `modules/` without prompting
- `--timeout`: wall-clock budget per subprocess; a timeout terminates the process group

## Example

```bash
cd <app-dir>
nsx clean
```

`--reset` is broader than a normal or `--full` clean. Review local module
changes before combining it with `--force`.

Run `nsx commands --json` for the authoritative machine-readable argument
schema.
