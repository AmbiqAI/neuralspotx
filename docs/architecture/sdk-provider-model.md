# SDK Provider Model

## Purpose

SDK provider modules decouple NSX board/SoC modules from hardcoded SDK paths and
allow explicit version-family selection across AmbiqSuite major lines.

## Provider Families

Current families:

1. `ambiqsuite-r3` (implemented)
2. `ambiqsuite-r4` (implemented)
3. `ambiqsuite-r5` (implemented)

For `ambiqsuite-r5`, board defaults may select different provider revisions
within the same repo lineage, for example `r5.1`, `r5.2`, `r5.2-alpha`, or
`r5.3`.

Provider modules:

1. `nsx-ambiqsuite-r3`
2. `nsx-ambiqsuite-r4`
3. `nsx-ambiqsuite-r5`

## Contracts

Each provider module is represented in metadata as:

1. `module.type = sdk_provider`
2. `module.category = sdk_provider`
3. `module.provider = ambiqsuite-r*`

Board modules bind to providers using:

1. required dependency on the provider module
2. `constraints.required_sdk_provider`

App metadata may further pin a provider revision using `nsx.yml` overrides:

1. `module_registry.projects.<provider-project>.revision`
2. `module_registry.modules.<provider-module>.revision`

This allows one provider repo such as `nsx-ambiqsuite-r5` to use different
branches or tags for different boards without pretending that all R5-family
targets come from one identical vendor drop.

NSX CLI enforces:

1. provider compatibility against board/soc/toolchain
2. provider dependency presence
3. no multiple SDK providers in one resolved module closure

Release-specific wrapper modules sit above the raw provider payload:

1. `nsx-ambiq-hal-r3` / `nsx-ambiq-hal-r4` / `nsx-ambiq-hal-r5`
2. `nsx-ambiq-bsp-r3` / `nsx-ambiq-bsp-r4` / `nsx-ambiq-bsp-r5`

These wrappers expose the stable NSX-facing build surfaces while the
`ambiqsuite-r*` modules remain mostly raw imported SDK drops.

## CMake Integration

Provider selection happens before board include via `nsx_select_sdk_provider(...)`:

1. sets `NSX_SDK_PROVIDER`
2. resolves `NSX_AMBIQSUITE_ROOT` (module-local vendored root first for R3/R4/R5)
3. sets `NSX_AMBIQSUITE_VERSION`
4. sets `NSX_SELECTED_SDK_TARGET`

Default root behavior:

1. vendored app-local root is checked first at `app/modules/nsx-ambiqsuite-r*/sdk`
2. sibling module repo roots are then checked at `/Users/adampage/Ambiq/neuralspot/nsx-modules/nsx-ambiqsuite-r*/sdk`
3. explicit overrides still supported via:
   - `NSX_AMBIQSUITE_R3_ROOT`
   - `NSX_AMBIQSUITE_R4_ROOT`
   - `NSX_AMBIQSUITE_R5_ROOT`

Revision selection behavior:

1. the lock registry provides a default provider revision
2. starter profiles may override that revision per board
3. generated apps persist the chosen revision in `nsx.yml`
4. future `west`-managed flows should use that persisted revision when syncing
   provider repos

The board composite target links:

1. selected SDK target (`nsx_sdk_ambiqsuite_r3` / `nsx_sdk_ambiqsuite_r4` / `nsx_sdk_ambiqsuite_r5`)
2. release-specific HAL + BSP wrappers through `nsx_soc_hal`
3. startup target (`nsx_startup`)

Current decomposition:

1. raw provider modules own the imported/generated AmbiqSuite payload under `sdk/`
2. `nsx-ambiq-hal-r*` owns common Ambiq HAL include surfaces, minimal utility
   sources, and the release-specific HAL prebuilt library
3. `nsx-ambiq-bsp-r*` owns the release-specific BSP include surface and prebuilt
   BSP library
4. board modules own NSX policy such as startup source selection, linker script
   selection, compile definitions, and debug/flash settings
5. `nsx-cmsis-startup` remains an NSX wrapper that compiles the startup/system
   sources selected by the board module

## AmbiqSuite Decomposition Policy

Core baseline (required):

1. HAL
2. BSP
3. CMSIS ARM + device integration (startup/system)
4. minimal utility sources used by core bring-up/logging

Essential but non-core:

1. USB stack modules (RS4/RS5 and only when required by profile)

Optional:

1. BLE/Cordio
2. network stacks
3. FreeRTOS
