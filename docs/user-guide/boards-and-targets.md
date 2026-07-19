# Boards and Targets

An NSX app can declare a set of supported board targets. One target is active
for each configure, build, flash, or view operation.

In `nsx.yml`, `targets.default` selects the target used when no command-line
override is provided, while `targets.supported` lists every board the app may
select. Each supported target resolves its own SoC, starter profile, and
optional toolchain override. For example:

```yaml
targets:
  default: apollo510_evb
  supported:
    - apollo510_evb
    - apollo4p_blue_kxr_evb
toolchain: arm-none-eabi-gcc
```

Use `--board` on app lifecycle commands to select another declared target.
NSX rejects boards that are not in `targets.supported`.

## Why This Model Exists

NSX is intentionally lightweight. Its target set is explicit app metadata,
not a device-tree abstraction layer.

This keeps:

- startup selection explicit
- linker selection explicit
- board wiring assumptions visible
- SDK provider choice deterministic

## Current Built-In Boards

- `apollo2_evb`
- `apollo3_evb`
- `apollo3_evb_cygnus`
- `apollo3p_evb`
- `apollo3p_evb_cygnus`
- `apollo4l_evb`
- `apollo4l_blue_evb`
- `apollo4p_evb`
- `apollo4p_blue_kbr_evb`
- `apollo4p_blue_kxr_evb`
- `apollo4p_evb_disp_shield_rev2`
- `apollo5b_evb`
- `apollo510_evb`
- `apollo510b_evb`
- `apollo510dL_evb`
- `apollo330mP_evb`

Run `nsx board list` for the authoritative installed list, or
`nsx board list --json` for registered board, SoC, CPU, provider, and
toolchain metadata in machine-readable form.

## How Target Selection Works

The active board comes from `--board` when supplied, then
`targets.default`. It determines:

- the SoC family
- startup and system sources
- linker behavior
- flash and SWO settings
- the default SDK provider family and revision

NSX keeps a combined `nsx.lock` with target-specific resolution data and uses
a board-specific build directory by default. This lets one app support several
boards without mixing their active build configuration.
