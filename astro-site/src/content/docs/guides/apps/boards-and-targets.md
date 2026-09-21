---
title: Boards and targets
description: How an NSX app declares the boards it targets, what a board definition provides, and how to build one app for several of them.
---

A board is the concrete thing NSX builds for. Picking one fixes the SoC, the CPU and ABI
flags, the startup and linker behavior, the flash and SWO settings, and which SDK provider
the app resolves against.

## What a board definition carries

Each packaged board is a directory under the NSX package holding a `board.yaml` descriptor
plus the CMake fragments that implement it. The descriptor for `apollo510_evb` is:

```yaml
schema_version: 1
board:
  name: apollo510_evb
  tier: evb
  soc: apollo510
  registered: true
sdk_provider: ambiqsuite
cpu:
  core: cortex-m55
  float_abi: hard
  abi: thumbv8.1m-fpv5-hard
toolchains:
  - arm-none-eabi-gcc
  - armclang
  - atfe
```

`toolchains` is the set the board declares it can be built with. `tier` distinguishes an
evaluation board from an FPGA platform. Every field is documented on the generated
[`board.yaml` reference](/neuralspotx/reference/config/board-yaml/).

Alongside `board.yaml` the board ships `board.cmake`, `bsp.cmake`, `soc.cmake`,
`memory.cmake` and `debug.cmake`. Those are what `nsx configure` vendors into
`boards/<board>/` in your app, and between them they select the startup file and the
linker script for the target. See
[Startup and linker](/neuralspotx/guides/system/startup-and-linker/).

## The packaged boards

```bash
nsx board list
```

```text
BOARD                          SOC         TIER     PROVIDER
apollo2_evb                    apollo2     evb      ambiqsuite
apollo330mP_evb                apollo330P  evb      ambiqsuite
apollo3_evb                    apollo3     evb      ambiqsuite
apollo3_evb_cygnus             apollo3     evb      ambiqsuite
apollo3p_evb                   apollo3p    evb      ambiqsuite
apollo3p_evb_cygnus            apollo3p    evb      ambiqsuite
apollo4l_blue_evb              apollo4l    evb      ambiqsuite
apollo4l_evb                   apollo4l    evb      ambiqsuite
apollo4p_blue_kbr_evb          apollo4p    evb      ambiqsuite
apollo4p_blue_kxr_evb          apollo4p    evb      ambiqsuite
apollo4p_evb                   apollo4p    evb      ambiqsuite
apollo4p_evb_disp_shield_rev2  apollo4p    evb      ambiqsuite
apollo510_evb                  apollo510   evb      ambiqsuite
apollo510b_evb                 apollo510b  evb      ambiqsuite
apollo510dL_evb                apollo510L  evb      ambiqsuite
apollo5b_evb                   apollo5b    evb      ambiqsuite
atomiq110_fpga_turbo           atomiq110   fpga     ambiqsuite
```

`nsx board list --json` adds the CPU core, float ABI, ABI string and declared toolchains
for each entry, and `nsx board show <board>` prints one board in full. The
[board matrix](/neuralspotx/modules/boards/) is the same data rendered as a page.

:::note[Board names and SoC names are not the same]
`apollo510dL_evb` targets the `apollo510L` SoC, and several Apollo4 boards share the
`apollo4p` SoC. Use the board name with `--board` and the SoC name only where a page or a
manifest explicitly asks for an SoC.
:::

## How an app declares its target

A freshly generated app declares one board:

```yaml
target:
  board: apollo510_evb
```

The manifest also accepts a multi-target form, which is what the packaged examples use:

```yaml
targets:
  default: apollo510_evb
  supported:
    - apollo510_evb
    - apollo510b_evb
    - apollo330mP_evb
    - apollo510dL_evb
    - apollo4p_blue_kxr_evb
```

`default` is the board used when you do not say otherwise. `supported` is the set that
`--board` will accept. Every field is on the generated
[`nsx.yml` reference](/neuralspotx/reference/config/nsx-yml/).

## Selecting a target for one run

```bash
nsx build --board apollo4p_blue_kxr_evb
```

`--board` works on `configure`, `build`, `flash`, `view` and `clean`. It does not change
`nsx.yml`; it selects which declared target this invocation acts on.

Each board gets its own `build/<board>/` directory, so switching back and forth does not
throw away the other target's build tree. `nsx.lock` likewise records one resolved module
set per board, because two boards on different SoC families can legitimately resolve
different modules.

## Adding a second target

1. Add the board to `targets.supported` in `nsx.yml`.
2. Run `nsx lock` so the new board gets its own resolved section in `nsx.lock`.
3. Build it with `nsx build --board <new-board>`.

If the new board's closure cannot be satisfied, the lock step is where you find out, not
the build. Source that needs to differ per family belongs in a per-family overlay rather
than behind preprocessor conditionals; see
[Multi-target and portability](/neuralspotx/guides/concepts/multi-target/).

## Boards NSX does not package

`nsx board create` scaffolds a board definition you own, which you then fill in with the
same fragments a packaged board ships. The practical constraint is that the SoC, the
startup path and the SDK provider have to line up before an app will build against it.
[Adding a board](/neuralspotx/guides/contribute/adding-a-board/) covers the work and the
order to do it in.

## Compatibility is declared

Every statement a board or a module makes about what it works with comes from a manifest
its author wrote. A board declaring `atfe` in `toolchains`, or a module declaring a board
in `compatibility.boards`, is a declaration of intent, not a record that the combination
was run on hardware. Treat the matrix as the starting point for a bring-up, not as
evidence of one.
