---
title: Adding a board
description: Scaffold a board definition, fill in its five CMake fragments and its descriptor, and get an app building against hardware NSX does not package.
---

NSX packages a board definition for every board in the
[board matrix](/neuralspotx/modules/boards/). Adding one of your own means writing a board
module: a descriptor that says what the board is, and the CMake fragments that wire it up.

Do this for a custom board or a variant of a packaged one. For a board that only differs
from a packaged one in a pin or two, starting from that board's definition and changing
the BSP fragment is far less work than starting from scratch.

## Scaffold it

```bash
nsx board create my_board --soc apollo510
```

See [`nsx board create`](/neuralspotx/reference/cli/board-create/) for the options. The
result is a directory with the same shape as a packaged board.

## What a board module contains

| File | What it does |
| --- | --- |
| `board.yaml` | The descriptor: name, tier, SoC, whether it is registered, the SDK provider, the CPU core, float ABI and ABI string, and the toolchains it declares. |
| `nsx-module.yaml` | The board as a module, so it resolves like any other. Type `board`. |
| `board.cmake` | Board-level flags and definitions, including the stack and heap sizes handed to the startup code. |
| `bsp.cmake` | Board support: pins, peripherals, the BSP sources from the SDK. |
| `soc.cmake` | SoC-level wiring shared by every board on that part. |
| `memory.cmake` | Startup source, CMSIS system source, and the linker script selection. |
| `debug.cmake` | Flash and SWO settings, which is what the generated SEGGER command files are built from. |

The descriptor and the manifest are both validated, and every field of each is documented
in the generated reference:
[`board.yaml`](/neuralspotx/reference/config/board-yaml/) and
[`nsx-module.yaml`](/neuralspotx/reference/config/nsx-module-yaml/).

## The order that works

1. **Get the descriptor right first.** The SoC, the CPU core, the float ABI and the ABI
   string decide every compiler flag that follows. A wrong ABI produces link errors that
   look like missing symbols.
2. **Make `memory.cmake` point at real files.** Copy the structure from the packaged board
   for the same SoC: the startup source and linker script live in the `nsx-core` module,
   per SoC and per toolchain family, and both a default and an ITCM variant are named. See
   [Startup and linker](/neuralspotx/guides/system/startup-and-linker/).
3. **Then `bsp.cmake`.** This is where a custom board actually differs. Everything above
   it is determined by the part.
4. **Generate an app against it and build.** `nsx create-app probe --board my_board
   --soc apollo510`, then `nsx configure` and `nsx build`. Configure is where a bad
   descriptor surfaces; build is where a bad fragment does.
5. **Then flash and view.** `debug.cmake` is the last thing to get right, and it is the
   only part you cannot check without hardware.

## The SDK provider has to resolve

A board that NSX does not recognize as registered cannot infer its SDK provider:

```text
Unable to infer SDK provider for board 'my_board'. Set -DNSX_SDK_PROVIDER=ambiqsuite.
```

NSX follows a custom board's parent link before giving up, so declaring the packaged board
you derived from is the clean fix. See
[SDK providers](/neuralspotx/guides/modules/sdk-providers/).

## Declaring compatibility honestly

`toolchains` in `board.yaml` and `compatibility` in `nsx-module.yaml` are how the rest of
the system reasons about your board, and they are enforced: a module whose compatibility
excludes your board will be rejected rather than built.

List what you have actually built, not what you expect to work. A board that declares all
three toolchains and has only been built with GCC produces failures for whoever tries the
other two, in a place that gives them no clue where the claim came from.

## Adding it to NSX itself

Everything above works in your own tree. Getting a board packaged with NSX, so that
`nsx board list` shows it for everyone, is a change to the NSX repository: the board
definition, the registry entry and the tests that cover both. That work starts with an
issue on [AmbiqAI/neuralspotx](https://github.com/AmbiqAI/neuralspotx/issues), and the
repository's `CONTRIBUTING.md` covers the development setup and review process.
