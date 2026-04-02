# `nsx doctor`

Checks the local NSX development environment.

This command is useful before creating an app, and it is the first command
to run when flash or view problems suggest a local tool issue rather than an app
issue.

## Syntax

```bash
nsx doctor
```

## What It Checks

- Python availability
- `uv`
- CMake
- Ninja
- Arm GNU toolchain
- `JLinkExe`
- `JLinkSWOViewerCL`
- basic SEGGER J-Link runtime startup

## Example

```bash
nsx doctor
```

## Notes

- `doctor` checks that the tools are installed and can start.
- it does not require a connected target board
- if SEGGER runtime startup fails, fix that before debugging `nsx flash` or
  `nsx view`
