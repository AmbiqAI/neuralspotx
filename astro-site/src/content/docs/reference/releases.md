---
title: Releases and versioning
description: How NSX versions are numbered and tagged, what the Provisional stability tier means, and how to pin a version you depend on.
---

NSX is published to PyPI as `neuralspotx`. Every release is cut from `main` by an
automated workflow, so what you install is always a commit that passed CI as it
stands, not a branch snapshot.

## Maturity and support

NSX 0.x is Beta. The approved 1.x support scope covers the current release
for evaluation and integration with modular CMake and AmbiqSuite, including
bring-up, profiling, validation and demos. Production support, long-term
support and backports are outside that commitment. Direct Zephyr and CMSIS-Pack
workflows are outside the tool's scope. Spark hardware qualification is
tracked separately. For Corstone virtual targets on the development branch, see
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/). Check the
[release notes](https://github.com/AmbiqAI/neuralspotx/releases) for availability
in your installed CLI. [Spark qualification](https://github.com/AmbiqAI/neuralspotx/issues/154)

## Cadence

There is no release calendar. Changes accumulate on `main` into a pending
release pull request, and a release happens when a maintainer merges it. Expect
releases in batches rather than on a fixed day.

Each release carries a changelog entry derived from the commit titles that went
into it. The full history is in
[CHANGELOG.md](https://github.com/AmbiqAI/neuralspotx/blob/main/CHANGELOG.md)
and on the
[releases page](https://github.com/AmbiqAI/neuralspotx/releases).

## Version and tag names

The version in `pyproject.toml` is the version. The git tag for a release is
that version with a package prefix:

| Version | Tag |
| --- | --- |
| `0.8.1` | `neuralspotx-v0.8.1` |
| `0.9.0` | `neuralspotx-v0.9.0` |

Tags are annotated and immutable. A published tag is never moved, deleted or
reused, so a tag you pin today points at the same commit indefinitely. Every
tag from `neuralspotx-v0.7.10` onward is annotated; most earlier ones are
lightweight, and the oldest is a bare `v0.1.0` with no package prefix. Those
stay as they are.

Numbering follows the usual major, minor, patch shape, driven by the kind of
change that landed: a new capability moves the minor, a fix moves the patch.
In 0.x, minor releases can change public behavior. Starting with 1.0,
incompatible changes to the documented public interfaces require a major release.

## What Provisional means

In 0.x, Python exports are **Provisional**. Applications can use them, but their
names, signatures and behavior can change in a minor release. In 1.x, the
documented Python and CLI interfaces follow the compatibility policy below.

## Upgrading an app from 0.9.9 to 1.0.0

Keep a copy of the app's committed `nsx.yml` and `nsx.lock`. If the manifest
records `tooling.nsx.major: 0`, update the existing `tooling.nsx` block to
`version: 1.0.0` and `major: 1` on an upgrade branch. Run the following with
the 1.0.0 CLI from the app directory:

```bash
nsx lock
nsx configure --frozen
nsx build --frozen
```

Plain lock refreshes every declared board. Configure and build select the default
board. Repeat both frozen commands with `--board <board>` for each additional
target you use, including boards previously prepared for direct CMake.

Review the manifest and lock diff together. A plain lock preserves compatible
Git pins and records the updated manifest hash. Verify the app on its target
before committing the upgrade. Apps without a recorded tool major can start
with `nsx configure --frozen` and their existing lock.

<span id="proposed-compatibility-policy-for-1x"></span>

## Compatibility policy for 1.x

Starting with 1.0, applications can retain their configuration, automation and
compatible locked Git dependencies when upgrading the tool within 1.x. The
provisional policy above applies to 0.x releases.

| Surface | A compatible 1.x change | A change that requires a new major version |
| --- | --- | --- |
| Public exports listed in `neuralspotx.__all__` and `neuralspotx.api.__all__` | Add an optional keyword that preserves existing calls and defaults. | Remove an export, require a new argument, or make an existing positional request field keyword-only. |
| Documented Python requests, results, enums, and exceptions | Add an optional request field with a compatible default. | Remove a result field, change a documented return type or enum member, or change which documented exception callers can catch. |
| Documented CLI commands, positional arguments, and flags | Add an optional flag. Help text and progress messages can evolve. | Reorder required arguments, rename a supported flag, change its default behavior incompatibly, or change the meaning of a documented exit code. |
| Documented CLI JSON output | Add an optional object field. Consumers should ignore unfamiliar keys. | Remove or rename a field, change its type or meaning, or add a value to an enumeration documented as closed. |
| Authored app, module, registry, and board configuration | Accept a new optional field while continuing to accept valid 1.0 files with their existing meaning. | Require an edit to a previously valid file or silently ignore a requirement that changes the dependency, target, or build. |
| Prepared apps using direct CMake | Add an optional CMake target or option. | Require Python to build an already prepared app, remove the documented toolchain entry point, or change how `NSX_BOARD` selects a prepared target. |
| Committed `nsx.lock` | Add optional diagnostic metadata that older readers can safely ignore. | Require a different lock schema to consume an existing valid 1.x lock, or select a different Git revision solely because the tool was upgraded. |

Authored files retain exact schema-version checks.
A new build requirement can use the existing version only if older tools
already reject its syntax or enforce it correctly. The default for an
incompatible authored or lock format change is to schedule it for 2.0.
Disposable caches can still be regenerated.

The compatibility promise includes the documented minimum board/BSP binding,
board selection, and public configure, flash, reset and RTT behavior. Private
debug snapshots, helper files, internal Python modules and undocumented output are
implementation details. Additional probe backends and dynamic plugins are outside
the 1.x commitment. Release notes announce deprecations of documented
interfaces and identify their replacements. Supported aliases deprecated
during 1.x keep working through the series. [Lock behavior](/neuralspotx/guides/modules/lock-and-sync/#1x-lock-behavior)

## Qualification baseline for 1.0

The table below records the pre-release baseline from [neuralspotx 0.9.9](https://github.com/AmbiqAI/neuralspotx/commit/05a5f51206343599bcf0e3e4a4a8a96e63319fcd)
and [nsx-ambiq-sdk 5.2.32](https://github.com/AmbiqAI/nsx-ambiq-sdk/commit/fc660806bacdfe4b9f84f1e2ea2bd9ada918cda6).

The 1.0.0 candidate rebuilt the locked Apollo510 `kws_infer` example with the
same firmware bytes as 0.9.9. A separate generated hello-world app was flashed
and ran on a physical Apollo510 EVB. The release owner approved publication,
and the published PyPI and GitHub artifacts matched the release checksums.
[Candidate and board results](https://github.com/AmbiqAI/neuralspotx/issues/226#issuecomment-7067585551)
· [Published artifact verification](https://github.com/AmbiqAI/neuralspotx/issues/226#issuecomment-7068207718)

| Configuration | What was verified |
| --- | --- |
| Linux, macOS and Windows | Python 3.11 and 3.13 tests and GCC example builds. Linux also ran ATfE example builds. The licensed Armclang example job was skipped. FreeRTOS blinky was compiled. Per-board scheduler behavior was outside that check. [Release CI](https://github.com/AmbiqAI/neuralspotx/actions/runs/44926578489) |
| Apollo510, installed CLI | The 0.9.9 candidate restored and built the locked `kws_infer` example with GCC. The lock stayed byte-identical. This was a host build. [Release qualification](https://github.com/AmbiqAI/neuralspotx/issues/226) |
| AP330 Plus, AP510, AP510B and AP510 Lite | The SDK linked minimal firmware and checked its layout using GCC, ATfE and ACfE. AP510 Lite has link coverage in this run. [SDK qualification](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.32/release/qualification-5.2.32.md) |
| AP3 Blue Plus, AP4 Blue Plus KXR, AP330 Plus, AP510 and AP510B EVBs | SDK startup, runtime and power checks ran with GCC and debugger reset. AP510B also passed over-the-air BLE GATT and reconnect checks. The generated power apps in this SDK run used CLI 0.9.7. [Board results](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.32/release/qualification-5.2.32.md) |
| Linux, AP510 EVB and external Apollo ICD | A prior debugger smoke at `4e07325` with SDK 5.2.30 exercised flash, reset, SWO and RTT. [Recorded probe configuration and results](https://github.com/AmbiqAI/neuralspotx/issues/226) |

### Reading license coverage

In the 0.9.9 registry, all 17 packaged boards and the tooling module declare
BSD-3-Clause at their module root. [Packaged declarations in 0.9.9](https://github.com/AmbiqAI/neuralspotx/pull/350)

Fourteen external module entries omit
path-scoped declarations at their pinned revisions. Their SBOM entries still
identify the components. Consult the upstream notices for the files you use.
[Audit of the external module pins](https://github.com/AmbiqAI/neuralspotx/issues/226#issuecomment-7063572501)

SDK 5.2.32 leaves four scopes explicitly unresolved. They cover the mixed
AmbiqSuite payload, two USB headers and one PSRAM driver. The SBOM records
`NOASSERTION` for these paths. If the payload changes, the SDK maintainer
must record a new decision on the affected scopes. The approval here covers
how NSX discloses those gaps. [SDK maintainer decision](https://github.com/AmbiqAI/nsx-ambiq-sdk/issues/73#issuecomment-7056564313)

The 1.0 wheel NOTICE must identify all required Python dependencies and
distinguish optional extras. [NOTICE correction](https://github.com/AmbiqAI/neuralspotx/issues/348)

## How to pin

For a standalone CLI, install the version used to qualify the app. For example:

```bash
uv tool install 'neuralspotx==1.0.1'
nsx --version
```

If the app manages its Python tools with uv, add NSX as a project dependency
and commit both `pyproject.toml` and `uv.lock`:

```bash
uv add 'neuralspotx==1.0.1'
```

On a fresh checkout of that app, run:

```bash
uv sync --locked
uv run --locked nsx --version
uv run --locked nsx configure --frozen
uv run --locked nsx build --frozen
```

Here `uv.lock` pins the Python environment, including the CLI. The app's
`nsx.lock` records the firmware modules for each board, including the SDK
provider. Commit both locks to preserve those selections. Commit any app-owned
module sources and make registered local sources available on each machine.
To reproduce firmware binaries, also record the host build environment, including the Arm compiler,
CMake and Ninja versions. To look up the exact SDK and upstream source, see [Which revision you are on](/neuralspotx/guides/modules/sdk-providers/#which-revision-you-are-on).

## Verifying what you installed

Each GitHub release carries the wheel, the source distribution and a
`SHA256SUMS` manifest covering both. The same files are on PyPI, byte for byte.

Ask the installed CLI for its distribution version:

```bash
nsx --version
```

or `uv tool list` if you installed it as a tool, `pipx list` if you used pipx.
