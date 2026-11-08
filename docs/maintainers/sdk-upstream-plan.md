# SDK Upstream Model

This document describes how the AmbiqSuite SDK is sourced and provisioned for
NSX board and SoC modules.

> **Status: unified.** NSX originally planned one upstream repo per AmbiqSuite
> major line. That plan has been superseded: all AmbiqSuite SoCs now resolve
> from a single **unified SDK repo**,
> [`nsx-ambiq-sdk`](https://github.com/AmbiqAI/nsx-ambiq-sdk), through a single
> provider module. The historical per-major plan is summarized at the end for
> context.

## Current Model

One repo, [`nsx-ambiq-sdk`](https://github.com/AmbiqAI/nsx-ambiq-sdk), vendors
the AmbiqSuite drop, the HAL/BSP wrappers, and the shared NSX module set for
every supported SoC (Apollo2 through Apollo5, plus the experimental atomiq110).
Stable resolution pins every SDK module and SoC family to the published
[`v5.2.30` release](https://github.com/AmbiqAI/nsx-ambiq-sdk/releases/tag/v5.2.30).
The immutable tag resolves to `acc97030b7158f81dc11f8df68fc43b8346f6dfe`.
The `nsx-ambiqsuite`, `nsx-ambiq-hal` and `nsx-ambiq-bsp` modules are thin
metadata views onto that same project and revision.

The [5.2.30 release record](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.30/release/nsx-ambiq-sdk-5.2.30.yaml)
records the cumulative `stable-2026.11.05-sbrk42` archive refresh: all 73
HAL/BSP archives were rebuilt with the invalid weak vendor `_sbrk` removed.
The reviewed 5.2.29 provider headers/sources remain unchanged; the artifact
manifest records the new archive provenance. XSPI, C++ compatibility and
EM9305 fixes remain intact, as do NSX's bounded allocator and force-link
protection. Cordio retains its separately recorded base and NSX changes.

The corrected provider passed GCC startup/runtime checks on AP330, AP510B
and AP4 Blue Plus KXR (21 Unity cases). These are debugger-controlled starts,
not cold-power-on or full peripheral qualification. No new USB/BLE traffic or
ATfE/ACfE physical qualification is claimed. AP3 microphone work remains
deferred, AP510L was not physically exercised, and AT110 remains experimental.
Exact revisions and exclusions are recorded in the
[SDK qualification report](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.30/release/qualification-5.2.30.md).

Board profiles depend on the provider module for their SoC family, and NSX
vendors the resolved SDK content into the generated app. See
[SDK providers](https://ambiqai.github.io/neuralspotx/guides/modules/sdk-providers/)
for how providers are selected and for the user-facing controls.

## Why a Single Repo

- one provenance story to explain, audit, and update
- no cross-repo version skew between the SDK drop, HAL/BSP wrappers, and shared
  module sources
- release lines are selected through module metadata, not through separate
  upstreams or branch pinning

## Apollo510L

Apollo510L is exposed through the board name `apollo510dL_evb`. The unified SDK
provides the CMSIS device files, system source, board headers, and prebuilt
HAL/BSP libraries that board requires.

## Historical Plan (superseded)

The original intent was one upstream repo per major line, with NSX board
defaults pinned to SDK-aligned release tags (for example `r5.2.0`):

1. an Apollo3 / Apollo3 Plus provider
2. an Apollo4 Lite / Apollo4 Plus provider
3. an Apollo510 / Apollo510B / Apollo510L / Apollo330P provider

The unified `nsx-ambiq-sdk` repo replaced this approach, removing the need for
per-major repos and per-release tag pinning.
