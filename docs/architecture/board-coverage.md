# Board Coverage

This document tracks the built-in board definitions currently supported by NSX.

## Built-In Boards

The tooling package currently includes built-in board definitions for:

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
- `apollo510dL_evb`
- `apollo330mP_evb`

These boards are supported by the generated-app flow and have been validated at
least through `nsx create-app`, `nsx configure`, and `nsx build`.

## Implementation Notes

- All Apollo-class boards (Apollo3 through Apollo510/Apollo330P) resolve through
  the single provider `nsx-ambiqsuite`
- board definitions are built into the tooling repo and vendored into generated
  apps
- modules are resolved from the packaged registry, cloned from their upstream
  repos, and vendored into generated apps by NSX
