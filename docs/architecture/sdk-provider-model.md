# SDK Provider Model

## Purpose

SDK provider modules decouple NSX board and SoC modules from hardcoded SDK paths
and make provider selection explicit across AmbiqSuite major lines.

## Provider Family

There is a single AmbiqSuite provider that mirrors the upstream monorepo
(all SoCs side-by-side):

1. `ambiqsuite`

Provider module:

1. `nsx-ambiqsuite`

## Provider Revisions

The provider is sourced from the unified SDK monorepo, which vendors the
AmbiqSuite drop, the HAL/BSP wrappers, and the shared NSX module set for
every supported SoC:

1. `ambiqsuite` → `nsx-ambiq-sdk` (`main`)

The provider module (`nsx-ambiqsuite`) and the SDK wrapper modules that the
bundle vendors resolve to the unified `nsx-ambiq-sdk` project by default. The
selected project and revision are persisted in generated app metadata.

## Contracts

Each provider module is represented in metadata as:

1. `module.type = sdk_provider`
2. `module.category = sdk_provider`
3. `module.provider = ambiqsuite`

Board modules bind to providers using:

1. a required dependency on the provider module
2. a required SDK provider constraint

## Wrapper Modules

Unified wrapper modules sit above the raw provider payload:

1. `nsx-ambiq-hal`
2. `nsx-ambiq-bsp`

These wrappers expose the stable NSX-facing build surfaces (gated per-SoC by
capability, e.g. PMU on Apollo5) while the `nsx-ambiqsuite` module remains a
mostly raw imported SDK drop.

## Root Resolution

Provider selection sets:

1. `NSX_SDK_PROVIDER`
2. `NSX_AMBIQSUITE_ROOT`
3. `NSX_AMBIQSUITE_VERSION`
4. `NSX_SELECTED_SDK_TARGET`

Resolution order:

1. vendored app-local SDK root under `app/modules/nsx-ambiqsuite/sdk`
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
