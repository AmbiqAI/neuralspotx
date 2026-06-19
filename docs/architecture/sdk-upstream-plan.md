# SDK Upstream Model

This document describes how the AmbiqSuite SDK is sourced and provisioned for
NSX board and SoC modules.

!!! info "Status: unified"
    NSX originally planned one upstream repo per AmbiqSuite major line
    (`nsx-ambiqsuite-r3`, `-r4`, `-r5`). That plan has been superseded: all
    AmbiqSuite SoCs now resolve from a single **unified SDK repo**,
    [`nsx-ambiq-sdk`](https://github.com/AmbiqAI/nsx-ambiq-sdk), through a
    single provider module. The historical per-major plan is summarized at the
    end for context.

## Current Model

One repo, [`nsx-ambiq-sdk`](https://github.com/AmbiqAI/nsx-ambiq-sdk), vendors
the AmbiqSuite drop, the HAL/BSP wrappers, and the shared NSX module set for
every supported SoC (Apollo2 through Apollo5). It tracks `main`.

The provider and wrapper modules NSX resolves are thin metadata views onto that
one project:

| Provider / wrapper module | Project | Revision |
|---|---|---|
| `nsx-ambiqsuite` | `nsx-ambiq-sdk` | `main` |
| `nsx-ambiq-hal` | `nsx-ambiq-sdk` | `main` |
| `nsx-ambiq-bsp` | `nsx-ambiq-sdk` | `main` |

Board profiles depend on the provider module for their SoC family, and NSX
vendors the resolved SDK content into the generated app. See
[SDK Provider Model](sdk-provider-model.md) for how providers are selected and
[SDK Provider Selection](../user-guide/sdk-provider-selection.md) for the
user-facing controls.

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

1. `nsx-ambiqsuite-r3` — Apollo3 / Apollo3 Plus boards
2. `nsx-ambiqsuite-r4` — Apollo4 Lite / Apollo4 Plus boards
3. `nsx-ambiqsuite-r5` — Apollo510 / Apollo510B / Apollo510L / Apollo330P boards

The unified `nsx-ambiq-sdk` repo replaced this approach, removing the need for
per-major repos and per-release tag pinning.
