# SDK Provider Model

## Purpose

SDK provider modules decouple NSX board and SoC modules from hardcoded SDK paths
and make provider selection explicit across AmbiqSuite major lines.

## Provider Families

Current families:

1. `ambiqsuite-r3`
2. `ambiqsuite-r4`
3. `ambiqsuite-r5`

Provider modules:

1. `nsx-ambiqsuite-r3`
2. `nsx-ambiqsuite-r4`
3. `nsx-ambiqsuite-r5`

## Provider Revisions

Provider revisions are board-selectable.

Examples:

1. `nsx-ambiqsuite-r3` uses `r3.1.1`
2. `nsx-ambiqsuite-r4` defaults to `r4.5.0`
3. `nsx-ambiqsuite-r5` may use `r5.1`, `r5.2`, `r5.2-alpha`, or `r5.3`

The selected revision is persisted in generated app metadata.

## Contracts

Each provider module is represented in metadata as:

1. `module.type = sdk_provider`
2. `module.category = sdk_provider`
3. `module.provider = ambiqsuite-r*`

Board modules bind to providers using:

1. a required dependency on the provider module
2. a required SDK provider constraint

## Wrapper Modules

Release-specific wrapper modules sit above the raw provider payload:

1. `nsx-ambiq-hal-r3`, `nsx-ambiq-hal-r4`, `nsx-ambiq-hal-r5`
2. `nsx-ambiq-bsp-r3`, `nsx-ambiq-bsp-r4`, `nsx-ambiq-bsp-r5`

These wrappers expose the stable NSX-facing build surfaces while the
`nsx-ambiqsuite-r*` modules remain mostly raw imported SDK drops.

## Root Resolution

Provider selection sets:

1. `NSX_SDK_PROVIDER`
2. `NSX_AMBIQSUITE_ROOT`
3. `NSX_AMBIQSUITE_VERSION`
4. `NSX_SELECTED_SDK_TARGET`

Resolution order:

1. vendored app-local SDK root under `app/modules/nsx-ambiqsuite-r*/sdk`
2. explicit override variables when provided

## Decomposition Policy

Raw provider repos carry the imported SDK payload.

Wrapper modules expose:

1. HAL include surfaces and prebuilt HAL libraries
2. BSP include surfaces and prebuilt BSP libraries
3. the minimal utility sources required by core bring-up

Board modules remain responsible for:

1. startup selection
2. linker selection
3. compile definitions
4. flash and SWO settings
