---
title: SDK foundation and overrides
description: Find the SDK selected for a board, trace an Ambiq build to its upstream source, and test a prepared SDK in a separate build directory.
---

## SDK provider

Each board descriptor selects an SDK provider for that target. Ambiq EVBs use
`ambiqsuite`, supplied by the `nsx-ambiqsuite` module in the `nsx-ambiq-sdk`
repository. Corstone virtual boards use a separate `corstone` provider. See
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/) for the targets
and commands supported by your CLI version.

Modules can declare `constraints.required_sdk_provider`. NSX checks the module
dependencies for each target and rejects a combination that requires two SDK providers.
A custom Ambiq board can supply its own board support package (BSP) while using
the same silicon support as the EVB. See [Add a board](/neuralspotx/guides/contribute/adding-a-board/).

## How NSX builds on AmbiqSuite

NSX vendors the SDK and its wrappers into the app. For a built-in Ambiq EVB,
the app compiles its own sources and the selected NSX wrapper sources. The
`nsx-ambiq-hal` and `nsx-ambiq-bsp` modules link the HAL and BSP static libraries
shipped for the selected part, board and toolchain. A change inside the vendor HAL
implementation therefore requires a matching rebuilt archive. A change in a
wrapper compiled by the app takes effect when you rebuild the app.

For example, SDK v5.2.32 records the files and SHA-256 hashes for its GCC, ATfE
and Arm Compiler for Embedded archives in its [artifact manifest](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.32/modules/nsx-ambiqsuite/sdk/artifact-manifest.yaml).

## Which revision you are on

Three versions answer different questions about an Ambiq build. Start in the app
directory and select the board you built.

| Question | Where to look |
| --- | --- |
| Which NSX CLI am I running? | Run `nsx --version`, or `uv run --locked nsx --version` for an app with a committed `uv.lock` and a project dependency on `neuralspotx`. Compare it with `targets.<board>.nsx_tool.version` in `nsx.lock`, which records the tool that wrote the lock. |
| Which NSX SDK did the app lock? | In `targets.<board>.modules.nsx-ambiqsuite`, read `constraint` for the requested revision and `resolved.commit` for the exact Git commit. `resolved.vendored_at` gives the project directory inside the app. |
| Which upstream AmbiqSuite source went into that SDK? | Open the release manifest at the **locked SDK revision**. For a snapshot intake, read `upstream.vendor_source_commit` for the SWS commit and `upstream.source_commit` for the prepared archive source. The manifest also records staged header corrections and the provenance of retained files. |

For example, an app locked to NSX SDK `v5.2.32` records SDK commit `fc660806ba`.
That SDK took in AmbiqSuite commit `3cfb7d5071` from November 5, 2026, and built
its HAL/BSP archives from prepared commit `83bd69c37e`. The NSX SDK tag identifies
our distribution. The release manifest identifies the upstream snapshot and patches.
[SDK v5.2.32 release manifest](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.32/release/nsx-ambiq-sdk-5.2.32.yaml)

The packaged registry supplies defaults for new resolutions. An existing app can
override those defaults or retain an earlier compatible Git resolution. To change
the SDK deliberately, follow [Pinning a module](/neuralspotx/guides/modules/lock-and-sync/#pinning-a-module)
and review the resulting lock diff for each board.

## Building against your own SDK tree

For a local experiment, point `--sdk-root` at a prepared AmbiqSuite payload
directory containing the headers and archives expected by the selected target.
Use a separate build directory so the experiment has its own CMake cache.
From an app targeting the Apollo510 EVB, for example:

```bash
nsx configure --board apollo510_evb --build-dir build/sdk-trial --sdk-root /path/to/prepared/sdk
nsx build --board apollo510_evb --build-dir build/sdk-trial --sdk-root /path/to/prepared/sdk
```

The override is local to the build. The app lock and SBOM still describe the
vendored SDK, so NSX rejects combining `--sdk-root` with `--frozen`. To build the
locked revision again, use the normal build directory and omit the override:

```bash
nsx configure --board apollo510_evb --frozen
nsx build --board apollo510_evb --frozen
```
