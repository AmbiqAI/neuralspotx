# Board Coverage

This document tracks built-in NSX board support relative to legacy neuralSPOT.

## Built-In Boards

The Python tooling currently includes built-in board definitions under
`src/neuralspotx/boards` for:

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

These boards are supported by the current generated-app flow and have been
validated at least through `nsx create-app`, `nsx configure`, and `nsx build`.

## Currently Blocked Legacy Targets

The following legacy neuralSPOT targets are not yet exposed as built-in NSX
boards:

- `apollo510L_eb`

`apollo510L_eb` remains blocked because the local SDK history does not yet give
us a clean BSP/lib bundle to vendor into the normalized `nsx-ambiqsuite-r5`
payload.

The newly supported R5-family boards (`apollo5b_evb`, `apollo510b_evb`, and
`apollo330mP_evb`) were enabled by importing the missing vendor assets into the
raw `nsx-ambiqsuite-r5` provider while keeping HAL/BSP consumption wrapper-based.

## Implementation Notes

- Apollo3-class boards resolve through `nsx-ambiqsuite-r3`.
- Apollo4 Lite and Apollo4 Plus boards resolve through `nsx-ambiqsuite-r4`.
- Apollo5B, Apollo510, Apollo510B, and Apollo330P-class boards resolve through `nsx-ambiqsuite-r5`.
- Board definitions are built into the Python tooling repo and vendored into
  generated apps.
- Modules remain external to the tooling repo and are vendored into apps from
  `nsx-modules`.
