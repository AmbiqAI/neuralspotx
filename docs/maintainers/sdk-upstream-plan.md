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
[`v5.2.28` release](https://github.com/AmbiqAI/nsx-ambiq-sdk/releases/tag/v5.2.28).
The immutable tag and regenerated example locks select the SDK content
qualified in [NSX PR #306](https://github.com/AmbiqAI/neuralspotx/pull/306).

The `nsx-ambiqsuite`, `nsx-ambiq-hal` and `nsx-ambiq-bsp` modules are thin
metadata views onto that same project and revision.

The [5.2.28 release record](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.28/release/nsx-ambiq-sdk-5.2.28.yaml)
adds shared-memory header-order/compiler integration fixes, BLE notification
timer lifecycle fixes and explicit rejection of unsupported AT110 timer
integration. The generated AmbiqSuite payload under `modules/nsx-ambiqsuite/sdk/`,
including all 73 HAL/BSP archives, remains unchanged from 5.2.27; wrapper
metadata reflects the new distribution version. This is not a new upstream
AmbiqSuite intake. Apollo330P and Apollo510L retain the SDK default DTCM layout.
Qualification scope, bounded AP510B debugger-reset evidence and exclusions are
recorded in the [SDK qualification report](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.28/release/qualification-5.2.28.md).

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
