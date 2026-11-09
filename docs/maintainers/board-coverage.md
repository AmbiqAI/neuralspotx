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
- `atomiq110_fpga_turbo` (preview channel; Atomiq110 FPGA bring-up target)

These descriptors are registered in the packaged board table and available to
the generated-app flow. Run `nsx board list --registered-only` for the
authoritative list in the installed version, or add `--json` for structured
board, SoC, provider, CPU, and toolchain data. Boards marked *preview* are
published on the registry's `preview` channel (`board_profiles` in
`registry.lock.yaml`); preview boards may track in-flight bring-up, and no
additional gating is applied by `nsx create-app`.

## Implementation Notes

- All Apollo-class boards (Apollo2 through Apollo510/Apollo330P) resolve through
  the single provider `nsx-ambiqsuite`
- board definitions are built into the tooling repo and vendored into generated
  apps as required by their declared targets
- modules are resolved from the packaged registry, cloned from their upstream
  repos, and vendored into generated apps by NSX

## AT110 Ownership Across NSX and SDK

`neuralspotx` owns the explicit packaged registry binding and app-facing board
module for `nsx-board-atomiq110-fpga-turbo`. `nsx-ambiq-sdk` retains its standalone
board descriptor and concrete HAL/BSP integration. Neither directory discovery
nor the existence of two manifests changes the default registry owner. Explicit
app registry overrides and app-local vendoring retain their normal precedence.

The SDK owns the cross-repository checker and immutable NSX manifest snapshot in
`tools/check_at110_board_compatibility.py` and
`tests/fixtures/board-compatibility/at110-nsx.json`. Normal SDK CI compares its
current manifest with this local fixture; NSX tests guard the explicit registry
owner, app overrides, and descriptor/manifest agreement. There is no implicit
sibling checkout or network dependency in either test suite.

Before promoting a shared AT110 metadata change, the changing maintainer runs
this command from the SDK checkout being adopted:

```sh
uv run --group ci python tools/check_at110_board_compatibility.py \
  --nsx-repo /explicit/neuralspotx/checkout --revision FULL_NSX_COMMIT_SHA
```

The exact commit must come from the trusted upstream. The command reads committed
Git objects; uncommitted files are not checked. The promotion reviewer verifies
this evidence. Add `--refresh` only to prepare a reviewed SDK fixture update after
a compatible check. A snapshot cannot detect later changes in the other repository
without this explicit promotion check. See the SDK's contributing guide for the
field contract and refresh procedure.

For AT110, shared support sets must match regardless of order. Independent module
versions need not match. This is a manifest compatibility check; existing board
CMake/configure, closure and vendoring tests remain necessary. It does not establish
hardware qualification. Other board pairs differ in identity/support and require
classification before extending this check. Shared-fact authorship and the
helia-platforms boundary remain in the joint #154/#152 proposal; this does not
introduce a catalog dependency or migrate board ownership.
