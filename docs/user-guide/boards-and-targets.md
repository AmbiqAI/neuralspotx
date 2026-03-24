# Boards and Targets

NSX apps are single-target by design.

Each app pins:

- one board
- one SoC
- one toolchain

## Why This Model Exists

NSX is intentionally lightweight. It does not try to recreate a multi-board
device-tree abstraction layer.

This keeps:

- startup selection explicit
- linker selection explicit
- board wiring assumptions visible
- SDK provider choice deterministic

## Current Built-In Boards

- `apollo3_evb`
- `apollo3_evb_cygnus`
- `apollo3p_evb`
- `apollo3p_evb_cygnus`
- `apollo4l_evb`
- `apollo4l_blue_evb`
- `apollo4p_evb`
- `apollo4p_blue_kbr_evb`
- `apollo4p_blue_kxr_evb`
- `apollo5b_evb`
- `apollo510_evb`
- `apollo510b_evb`
- `apollo330mP_evb`

## How Target Selection Works

The selected board determines:

- the SoC family
- startup and system sources
- linker behavior
- flash and SWO settings
- the default SDK provider family and revision
