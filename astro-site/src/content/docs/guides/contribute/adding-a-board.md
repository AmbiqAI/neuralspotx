---
title: Add a board
description: Select a custom BSP provider while sharing SDK silicon support.
---

A custom board owns its identity, package and pin choices, peripherals, and debug
configuration. The SDK owns silicon support and the BSP interface. NSX resolves and
vendors the selected modules into the app.

## Scaffold the board

From an existing app, run:

```bash
nsx board create my_board --from apollo330mP_evb --bsp-module my-bsp
```

This creates `boards/my_board/` with a descriptor, module manifest, CMake bootstrap,
and a module entry point. It snapshots the parent's descriptor into the app.
Inheritance shares SoC, CPU, SDK-provider, and toolchain facts. It does not include
the parent's EVB CMake, pins, package definitions, or BSP binding.

The new descriptor explicitly selects a BSP:

```yaml
schema_version: 2
inherits: apollo330mP_evb
board:
  name: my_board
  tier: custom
  registered: false
roles:
  bsp:
    module: my-bsp
    contract: 2
```

You can add `board.revision` to distinguish hardware revisions. Keep the board
identity stable if its BSP later moves into the SDK; change the explicit binding.

## Supply a BSP module

The scaffold does not implement hardware support. Register your BSP as a module,
or add an app-owned `modules/my-bsp/` with `source: {vendored: true}` in `nsx.yml`.
The selected BSP needs a complete `nsx-module.yaml`, including its dependencies.
Its additional contract declaration is:

```yaml
contracts:
  provides:
    bsp:
      versions: [2]
      socs: [apollo330P]
```

A consumer declares `depends.required` with `{role: bsp, contracts: [2]}` or
`[1, 2]` if it implements both versions. Versions are explicit alternatives;
version 2 does not implicitly satisfy version 1. A concrete `nsx-ambiq-bsp`
dependency conflicts with a custom binding.

The BSP's CMake registers its concrete target using the SDK helper:

```cmake
add_library(my_bsp STATIC bsp.c)
target_link_libraries(my_bsp PUBLIC nsx_ambiq_hal nsx::board_flags)
nsx_register_bsp(TARGET my_bsp CONTRACT 2 DEBUG_ITM 0 DEBUG_UART 0)
```

Implement the SDK's required BSP functions and headers. Debug capability values
belong to the CMake target, not duplicated YAML. Contract 2 currently requires an
SDK revision with that contract implementation and is qualified only for
Apollo330P and Apollo510. The packaged stable SDK pin is not automatically changed
by scaffolding a custom board; select a compatible immutable SDK revision through
an explicit app registry override.

## Configure and qualify

Set the app's target board to `my_board`. NSX derives the baseline from the SoC
family, substitutes the selected BSP seed, and adds the custom board module.
The SDK supplies silicon flags, startup, and the default linker layout. Optional
local `flags.cmake`, `memory.cmake`, and `debug.cmake` fragments supply reviewed
board-specific choices. No EVB probe identity is inherited.

Run `nsx lock`, `nsx sync`, `nsx configure`, and `nsx build`. Each target's lock
records the board binding and descriptor/contract-manifest fingerprints (CRLF
line endings normalize to LF; all other bytes remain significant).
Changing these inputs requires a new lock; frozen builds reject drift. Board
schema 1 must be updated explicitly to schema 2, and old locks regenerated.

On a clean checkout, read-only `nsx lock --check` can reuse the recorded closure
and unavailable contract fingerprints. It warns that missing metadata cannot be
certified, and still checks every available contract input and board descriptor.
Run `nsx sync` first for a complete check. Writable lock generation and frozen
sync/build verification require the actual metadata. Writable locks verify Git
contract inputs against the exact resolved artifacts. If those artifacts change
the dependency graph compared with the app-local sources, locking stops before
writing; refresh those sources to the selected revisions and lock again.

Configure the correct probe device before flashing. A successful host build does
not qualify pins, peripheral power sequencing, or hardware behavior. Narrow the
descriptor and module compatibility declarations to the combinations you support.
