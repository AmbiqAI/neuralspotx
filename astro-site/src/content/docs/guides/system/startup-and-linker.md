---
title: Startup and linker
description: Which startup file and linker script your board selects, where they come from, and how to override the selection.
---

Nothing in a generated app hides the startup path. The board fragment vendored into
`boards/<board>/` names the startup source and the linker script explicitly, and both are
files you can open.

## The board decides

`boards/<board>/memory.cmake` is the fragment that does it. For `apollo510_evb` it reads:

```cmake
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo510.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510/armclang/linker_script_sbl.sct")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510/armclang/linker_script_itcm_sbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo510.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510/gcc/linker_script_sbl.ld")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510/gcc/linker_script_itcm_sbl.ld")
endif()
```

Three things follow from that.

**The startup file comes from the `nsx-core` module, per SoC and per toolchain family.**
Arm Compiler for Embedded gets `startup_keil6.c`; GCC and ATfE get `startup_gcc.c`. Both
live under `modules/.../nsx-core/src/<soc>/` in your app.

**The CMSIS system file comes from the SDK**, under `NSX_AMBIQSUITE_ROOT`, not from NSX.
Which SDK tree that is depends on the provider resolution described in
[SDK providers](/neuralspotx/guides/modules/sdk-providers/).

**Linker scripts are per SoC, per toolchain and per profile.** Arm Compiler for Embedded
uses scatter files (`.sct`); GCC and ATfE use linker scripts (`.ld`).

## Bootloader and no-bootloader variants

Scripts come in two families, named for whether the image sits behind Ambiq's secure
bootloader:

- `linker_script_sbl.*`, the secure-bootloader layout, used by the Apollo boards.
- `linker_script_nbl.*`, the no-bootloader layout, used by `atomiq110_fpga_turbo`.

The difference is where the image starts in non-volatile memory, which is why an image
built for one will not run under the other. Your board's fragment picks the right one; you
do not choose between them.

## The ITCM profile

Each board names two scripts, a default and an ITCM variant, and hands both to a selector:

```cmake
if(COMMAND nsx_select_linker_script)
    nsx_select_linker_script(
        DEFAULT "${_nsx_linker_script_default}"
        ITCM "${_nsx_linker_script_itcm}"
    )
else()
    # SDK predates named linker profiles — fall back to the default script.
    set(NSX_LINKER_SCRIPT "${_nsx_linker_script_default}")
endif()
```

Setting `NSX_LINKER_PROFILE` to `itcm` selects the ITCM variant, which lays the image out
to execute from tightly coupled instruction memory rather than from NVM. That is the
layout the `coremark` example uses, and it is the one to reach for when instruction fetch
is what you are measuring.

`nsx_select_linker_script` is provided by the `nsx-core` module rather than by NSX itself,
which is why the fragment guards on `if(COMMAND ...)`. Against an SDK revision that
predates the feature, the default script is used and the profile is ignored.

## Overriding the script

The whole selection is skipped if `NSX_LINKER_SCRIPT` is already set:

```cmake
if(NOT DEFINED NSX_LINKER_SCRIPT)
```

So pointing the build at a script of your own is one CMake variable:

```bash
nsx configure -- -DNSX_LINKER_SCRIPT=/path/to/my_layout.ld
```

Start from the script your board would have selected, since it already has the correct
regions and section names for the part. The `power_benchmark` example ships its own
`linker_script_itcm.ld` for exactly this reason, and it is a readable starting point.

:::caution[An override is yours to maintain]
The vendored scripts change when the SDK revision your app pins changes. A copy you took
does not. Diff yours against the current one after an `nsx update` that moves the SDK.
:::

## Stack and heap

The board's `board.cmake` passes the startup code its stack and heap sizes as compile
definitions, for example:

```cmake
# STACK_SIZE: startup C-runtime stack size in bytes (used by SDK startup).
STACK_SIZE=4096
```

The startup source in `nsx-core` is what consumes them, and it is the file to read if you
need to know exactly how a given SDK revision interprets the value. Both come out of the
same region as your data, so raising either one takes space from everything else placed
there. See [Memory placement](/neuralspotx/guides/system/memory-placement/).

## What you get after linking

`build/<board>/` holds the linked ELF, a `.bin` and a `.map`. The map file is the record
of what actually ended up where: if you placed something with an `NSX_MEM_` macro and want
to confirm it landed in the region you meant, the map is the evidence, not the source.
