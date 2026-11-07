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
[`v5.2.29` release](https://github.com/AmbiqAI/nsx-ambiq-sdk/releases/tag/v5.2.29).
The immutable tag resolves to `5585350def5fdced39d42bba150042f92f23cf18`.
The `nsx-ambiqsuite`, `nsx-ambiq-hal` and `nsx-ambiq-bsp` modules are thin
metadata views onto that same project and revision.

The [5.2.29 release record](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.29/release/nsx-ambiq-sdk-5.2.29.yaml)
records the `stable-2026.11.05` intake: all 73 HAL/BSP archives were rebuilt
from a prepared upstream snapshot with reviewed XSPI storage patches. It also
includes the staged C++ compatibility and EM9305 fixes. Cordio retains its
separately recorded base and selected NSX changes.

The SDK passed five-board GCC integration comparisons plus bounded AP510 USB
and AP510B BLE traffic checks. That evidence is debugger-reset testing, not
cold-power-on or full peripheral qualification. AP3 microphone work remains
deferred, AP510L was not physically exercised, and AT110 remains experimental.
Exact revisions and exclusions are recorded in the
[SDK qualification report](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.29/release/qualification-5.2.29.md).

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
