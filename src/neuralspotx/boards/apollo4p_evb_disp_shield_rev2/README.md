# nsx-board-apollo4p-evb-disp-shield-rev2

Built-in NSX board definition for the Apollo4 Plus EVB fitted with the
Apollo4 Plus Display Kit shield (AmbiqSuite board
`apollo4p_evb_disp_shield_rev2`).

- Same Apollo4P silicon/package as `apollo4p_evb`; the shield adds populated
  PSRAM (APS25616N, MSPI) and a display interface not present on the plain
  EVB.
- Hardware-validated: `nsx-psram` XIP read/write via DMA, zero mismatches.
- Packaged with the NSX Python tooling repo.
- Vendored into generated apps under `boards/apollo4p_evb_disp_shield_rev2/`.
