# Board Coverage

This document tracks the built-in board definitions currently supported by NSX.

## Built-In Boards

The tooling package currently includes built-in board definitions for:

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

These descriptors are registered in the packaged board table and available to
the generated-app flow. Run `nsx board list --registered-only` for the
authoritative list in the installed version, or add `--json` for structured
board, SoC, provider, CPU, and toolchain data.

## Implementation Notes

- All Apollo-class boards (Apollo2 through Apollo510/Apollo330P) resolve through
  the single provider `nsx-ambiqsuite`
- board definitions are built into the tooling repo and vendored into generated
  apps as required by their declared targets
- modules are resolved from the packaged registry, cloned from their upstream
  repos, and vendored into generated apps by NSX
