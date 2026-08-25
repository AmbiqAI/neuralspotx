# nsx-board-atomiq110-fpga-turbo

Built-in NSX board definition for the Atomiq110 FPGA turbo bring-up target
(preview channel).

- Packaged with the NSX Python tooling repo.
- Vendored into generated apps under `boards/atomiq110_fpga_turbo/`.
- Startup and linker assets come from the `nsx-core` module
  (`src/atomiq110/{gcc,armclang}/`), selecting the no-bootloader (`nbl`)
  scripts because the FPGA loads directly via J-Link.
