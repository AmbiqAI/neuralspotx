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
Custom Apollo330P and Apollo510 boards can supply their own board support
package (BSP) while using the SDK silicon support. See [Add a board](/neuralspotx/guides/contribute/adding-a-board/).

## How NSX builds on AmbiqSuite

NSX vendors the SDK and its wrappers into the app. For a built-in Ambiq EVB,
the app compiles its own sources and the selected NSX wrapper sources. The
`nsx-ambiq-hal` and `nsx-ambiq-bsp` modules link the HAL and BSP static libraries
shipped for the selected part, board and toolchain. A change inside the vendor HAL
implementation therefore requires a matching rebuilt archive. A change in a
wrapper compiled by the app takes effect when you rebuild the app.

For example, SDK v5.2.33 records the files and SHA-256 hashes for its GCC, ATfE
and Arm Compiler for Embedded archives in its [artifact manifest](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.33/modules/nsx-ambiqsuite/sdk/artifact-manifest.yaml).

## Which revision you are on

Three versions answer different questions about an Ambiq build. Start in the app
directory and select the board you built.

| Question | Where to look |
| --- | --- |
| Which NSX CLI am I running? | Run `nsx --version`, or `uv run --locked nsx --version` for an app with a committed `uv.lock` and a project dependency on `neuralspotx`. Compare it with `targets.<board>.nsx_tool.version` in `nsx.lock`, which records the tool that wrote the lock. |
| Which NSX SDK did the app lock? | Open `targets.<board>.modules.nsx-ambiqsuite`. For a Git entry, `constraint` names the requested revision and `resolved.commit` gives the exact commit. For app-owned or local sources, `resolved.vendored_at` locates the app’s copy. Look up an external `source.path` or registry `local_path` in `nsx.yml` and the workspace registry files it references. |
| Which upstream AmbiqSuite source went into that SDK? | For a published SDK, read the release manifest at the **locked SDK revision**. Check the provenance of the specific headers or archives you use. For an unreleased or custom SDK, consult the provider’s artifact manifest or build records. |

For example, an app locked to NSX SDK `v5.2.33` records SDK commit `afc21d0bd9`.
Its manifest identifies the AmbiqSuite snapshot from November 5, 2026 as
`upstream.vendor_source_commit` (`3cfb7d5071`) and the prepared source for its
HAL/BSP archives as `upstream.source_commit` (`83bd69c37e`). The NSX SDK tag identifies
our distribution. The release manifest identifies the upstream snapshot and patches.
[SDK v5.2.33 release manifest](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.33/release/nsx-ambiq-sdk-5.2.33.yaml)

The packaged registry supplies defaults for new resolutions. An existing app can
override those defaults or retain an earlier compatible Git resolution. To change
the SDK deliberately, follow [Pinning a module](/neuralspotx/guides/modules/lock-and-sync/#pinning-a-module)
and review the resulting lock diff for each board.

## Building against your own SDK tree

For a local experiment, point `--sdk-root` at a prepared AmbiqSuite payload
directory containing the headers and archives expected by the selected target.
A separate build directory makes it easy to compare the trial with the locked
build. From an app targeting the Apollo510 EVB, run both commands with the same
SDK root and build directory.

```bash
nsx configure --board apollo510_evb --build-dir build/sdk-trial --sdk-root /path/to/prepared/sdk
nsx build --board apollo510_evb --build-dir build/sdk-trial --sdk-root /path/to/prepared/sdk
```

With SDK v5.2.33, default HAL and BSP archive paths follow the SDK root when
you reuse a build directory. Explicit archive pins keep their selected paths.
If CMake reports an ambiguous archive path cached by an older SDK, use a fresh
build directory or follow the diagnostic to clear or explicitly pin that entry.
For a Ninja build, `ninja -C build/sdk-trial -t commands <app-target>` shows
the paths to `libam_hal.a` and `libam_bsp.a` in the link command.

The override is local to the build. The app lock and SBOM still describe the
vendored SDK, so NSX rejects combining `--sdk-root` with `--frozen`. To build the
locked revision again, use the normal build directory and omit the override:

```bash
nsx configure --board apollo510_evb --frozen
nsx build --board apollo510_evb --frozen
```
