---
title: Toolchain support
description: The three cross compilers NSX generates for, how one is selected, what differs between them, and which is experimental.
---

NSX generates a CMake toolchain file per build and points CMake at it. Three cross
compilers are wired, and which one you get is a per-app setting you can override per run.

## The three

| Name | Toolchain file | Compiler |
| --- | --- | --- |
| `arm-none-eabi-gcc` | `arm-none-eabi-gcc.cmake` | Arm GNU Toolchain. The default. |
| `gcc` | `arm-none-eabi-gcc.cmake` | An alias for the above. |
| `armclang` | `armclang.cmake` | Arm Compiler for Embedded. |
| `atfe` | `atfe.cmake` | Arm Toolchain for Embedded. |

`arm-none-eabi-gcc` is the default, it builds every packaged example, and it is the only
one you need installed to get started. Anything else is rejected with the list:

```text
Unknown toolchain 'clang'. Supported: arm-none-eabi-gcc, armclang, atfe, gcc
```

The toolchain files themselves are vendored into your app at `cmake/nsx/toolchains/`, so
the exact flags any of them sets are readable in the app rather than hidden in the tool.

:::caution[ATfE is experimental]
NSX classifies `atfe` as functional but not fully validated for production use, and warns
every time you select it:

```text
Toolchain 'atfe' is experimental and not fully validated for production use.
```

Use it to evaluate the toolchain, not to ship.
:::

## Selecting one

Per app, in `nsx.yml`:

```yaml
toolchain: arm-none-eabi-gcc
```

Per run, on the command line:

```bash
nsx build --toolchain armclang
```

`--toolchain` is accepted by `configure`, `build`, `flash`, `view` and `clean`. Boards also
declare which toolchains they support in `board.yaml`, and that list is what the
[board matrix](/neuralspotx/modules/boards/) shows. As everywhere else in NSX, a declared
toolchain is a claim by the board's author, not a record of a build that was run.

Generated apps also ship `cmake/presets/CMakePresets.json` with a preset per toolchain,
`gcc-ninja`, `armclang-ninja` and `atfe-ninja`, so an IDE can open the project and pick
one without going through the CLI.

## What differs between them

Most of a build is the same either way. Three things are not.

**The compile definitions.** Portable code that needs to know what compiled it can test
for `NSX_TOOLCHAIN_GCC`, `NSX_TOOLCHAIN_ARMCLANG` or `NSX_TOOLCHAIN_ATFE`. GCC and ATfE
additionally define `gcc`, because both present a GCC-compatible surface to SDK code that
predates ATfE existing.

**The linker input.** GCC and ATfE take a linker script with `-T`; Arm Compiler for
Embedded takes a scatter file with `--scatter`. That is why every board names both a `.ld`
and a `.sct` variant. See
[Startup and linker](/neuralspotx/guides/system/startup-and-linker/).

**The startup source.** Arm Compiler for Embedded uses `startup_keil6.c`; GCC and ATfE use
`startup_gcc.c`.

Source that needs to differ per compiler should test the `NSX_TOOLCHAIN_*` definitions
rather than the compiler's own macros, because `__GNUC__` is true under ATfE as well.
Attribute-level differences are already abstracted: `NSX_SECTION`, `NSX_ALIGNED`,
`NSX_WEAK` and the rest in `nsx_compiler.h` expand correctly under all three. See
[Memory placement](/neuralspotx/guides/system/memory-placement/).

## Checking what you have installed

```bash
nsx doctor
```

The Arm GNU Toolchain is a required check. Arm Compiler for Embedded and ATfE are reported
only when they are present, so a clean report does not mean you have all three. See
[Check your environment](/neuralspotx/getting-started/doctor/).

## Switching an existing app

Each toolchain produces its own build tree, so switching is not destructive, but the
generated tree is configured for one of them at a time:

```bash
nsx clean --full
nsx build --toolchain armclang
```

Re-running `configure` with a different `--toolchain` against an existing build directory
is the case worth avoiding, because CMake caches the compiler. Clean first.
