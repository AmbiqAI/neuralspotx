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
Stable resolution uses the immutable `v5.2.26` release for every SoC family.

The provider and wrapper modules NSX resolves are thin metadata views onto that
one project:

| Provider / wrapper module | Project | Revision |
|---|---|---|
| `nsx-ambiqsuite` | `nsx-ambiq-sdk` | `v5.2.26` |
| `nsx-ambiq-hal` | `nsx-ambiq-sdk` | `v5.2.26` |
| `nsx-ambiq-bsp` | `nsx-ambiq-sdk` | `v5.2.26` |

`v5.2.26` is the release recorded in
[`release/nsx-ambiq-sdk-5.2.26.yaml`](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.26/release/nsx-ambiq-sdk-5.2.26.yaml)
(AmbiqAI/nsx-ambiq-sdk#84). Before it, the Apollo families resolved `v5.2.24`
and atomiq110 resolved `v5.2.25`. Moving every family to one release brings:

- the clang C++ fixes to the AmbiqSuite headers, so C++ applications build
  with ATfE on every SoC (nsx-ambiq-sdk #81, #83; upstream fix tracked in #82);
- the heap symbols in the apollo2/apollo3/apollo3p GCC linker scripts, so
  GCC and ATfE applications link on Apollo3 and Apollo3 Blue Plus
  (nsx-ambiq-sdk #85, #86);
- the 5.2.25 content (atomiq110 platform, `nsx-npu`, `nsx-core`/`nsx-power`
  updates) for the Apollo families as well.

The non-atomiq110 HAL/BSP archives are byte-identical to `v5.2.24`. The
release record lists every changed file per upgrade path and the open known
deviations, including atomiq110's header/archive mismatch and C++ global
constructors on apollo2/3/3p (nsx-ambiq-sdk #87).

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
