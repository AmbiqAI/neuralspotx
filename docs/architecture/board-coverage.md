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
- `apollo330mP_evb`

These boards are supported by the generated-app flow and have been validated at
least through `nsx create-app`, `nsx configure`, and `nsx build`.

## Currently Unavailable Target

- `apollo510L_eb`

`apollo510L_eb` remains unavailable because the current SDK history does not yet
provide a clean BSP and library bundle for the board.

## Implementation Notes

- Apollo3-class boards resolve through `nsx-ambiqsuite-r3`
- Apollo4 Lite and Apollo4 Plus boards resolve through `nsx-ambiqsuite-r4`
- Apollo5B, Apollo510, Apollo510B, and Apollo330P-class boards resolve through
  `nsx-ambiqsuite-r5`
- board definitions are built into the tooling repo and vendored into generated
  apps
- modules remain external to the tooling repo and are vendored into apps from
  `nsx-modules`
