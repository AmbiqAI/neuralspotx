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
[`v5.2.33` release](https://github.com/AmbiqAI/nsx-ambiq-sdk/releases/tag/v5.2.33).
The immutable tag resolves to `afc21d0bd97cb3e560891026b464708767f873fa`.
The `nsx-ambiqsuite`, `nsx-ambiq-hal` and `nsx-ambiq-bsp` modules are thin
metadata views onto that same project and revision.

The [5.2.33 release record](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.33/release/nsx-ambiq-sdk-5.2.33.yaml)
identifies the same AmbiqSuite provider and 73 HAL/BSP archives as 5.2.32.
With 5.2.33, CMake follows the selected SDK root for its default HAL and BSP
archives and preserves explicit archive pins. If a build directory from an
older SDK reports an ambiguous cached archive, reconfigure CMake with
`-UNSX_HAL_LIB -UNSX_BSP_LIB` to use both defaults, or explicitly pin the
intended archive paths. Registry-managed apps require NSX 0.9.6 or newer to
resolve the BSP provider role, including on built-in EVBs.

The [SDK qualification report](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.33/release/qualification-5.2.33.md)
records a generated GCC app running on Apollo510 and 12 link checks across
Apollo330 Plus, Apollo510, Apollo510B and Apollo510 Lite with GCC, ATfE and ArmClang.

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
