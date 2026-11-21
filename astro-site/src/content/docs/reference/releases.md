---
title: Releases and versioning
description: How NSX versions are numbered and tagged, what the Provisional stability tier means, and how to pin a version you depend on.
---

NSX is published to PyPI as `neuralspotx`. Every release is cut from `main` by an
automated workflow, so what you install is always a commit that passed CI as it
stands, not a branch snapshot.

## Maturity and support

NSX is **Beta**, and it is supported for **evaluation**: bring-up, profiling,
validation and demos. Production support is not committed before 1.0. That is the
maturity and support tier Ambiq records for it in the HELIA portfolio, and it is
what the stability tier below and the pinning advice further down follow from.

Beta is a statement about the interface, not about whether the tool works: the
commands and the module registry are in daily use inside Ambiq. It means the
names are still allowed to move, so anything you automate against them should
pin a version.

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
NSX is pre-1.0, so a minor bump is allowed to change behavior that a 1.x minor
bump would not. Read the changelog before you take one.

## What Provisional means

Every name exported from the `neuralspotx` Python package is currently
**Provisional**.

- **Provisional** means the name is public and supported, and it may still
  change before 1.0. A signature can gain a parameter, a return type can become
  more specific, a name can move.
- **Stable** means frozen: after 1.0, removing a name or breaking its signature
  needs a major version bump.

Nothing is Stable yet. The tier is stated once at the top of each
[Python API](/neuralspotx/reference/api/) page rather than repeated per symbol,
and it will be revisited at 1.0.

The same caution applies to the CLI while NSX is pre-1.0: flags and output
formats can change in a minor release. The `--json` output of commands that
offer it is the most stable thing to build on, because it is what tooling reads.

## Proposed compatibility policy for 1.x

This proposal is under review for the first stable release. The provisional
policy above applies to 0.x today. The proposed promise is that an application
written for 1.0 can keep its configuration, automation, and locked Git
dependencies when its developer upgrades the NSX tool within 1.x.

| Surface | A compatible 1.x change | A change that requires a new major version |
| --- | --- | --- |
| Documented Python exports from `neuralspotx` and `neuralspotx.api` | Add an optional keyword that preserves existing calls and defaults. | Remove an export, require a new argument, or make an existing positional request field keyword-only. |
| Documented CLI commands and flags | Add an optional flag. Help text and progress messages can evolve. | Rename a supported flag, change its default behavior incompatibly, or change the meaning of a documented exit code. |
| Documented CLI JSON output | Add an optional object field. Consumers should ignore unfamiliar keys. | Remove or rename a field, change its type or meaning, or add a value to an enumeration documented as closed. |
| Authored app, module, registry, and board configuration | Accept a new optional field while continuing to accept valid 1.0 files with their existing meaning. | Require an edit to a previously valid file or silently ignore a requirement that changes the dependency, target, or build. |
| Committed `nsx.lock` | Add optional diagnostic metadata that older readers can safely ignore. | Require a different lock schema to consume an existing valid 1.x lock, or select a different Git revision solely because the tool was upgraded. |

For authored files, the proposed policy keeps exact schema-version checks.
A new build requirement can use the existing version only if older tools
already reject its syntax or enforce it correctly. The default for an
incompatible authored or lock format change is to schedule it for 2.0.
Disposable caches can still be regenerated.

The 1.0 freeze would identify the supported exports, documented commands,
schemas, and board/provider interfaces. Internal Python modules and
undocumented output remain implementation details. A supported alias
deprecated during 1.x would keep working throughout the series. The release
notes would name its replacement before removal in a major release.
The proposed support window covers the current release for evaluation and
integration. SDK pins, toolchains, and physical board qualification have their
own release and acceptance decisions.

See the [proposed 1.x lock behavior](/neuralspotx/guides/modules/lock-and-sync/#proposed-1x-lock-behavior)
for the difference between upgrading the CLI and updating dependencies.
The scope and qualification decisions are tracked in [the v1 readiness issue](https://github.com/AmbiqAI/neuralspotx/issues/226).

## How to pin

Pin an exact version anywhere NSX is a dependency of something you ship or
automate.

```bash
# One-off tool install
uv tool install neuralspotx==0.8.1

# Project dependency
uv add "neuralspotx==0.8.1"
```

In a `pyproject.toml`:

```toml
dependencies = ["neuralspotx==0.8.1"]
```

A compatible-release constraint such as `~=0.8.1` allows patch updates and is
reasonable for local development. It is not enough for a build you need to
reproduce, because pre-1.0 patch releases still carry behavior fixes. For CI,
pin exactly and record the version alongside the artifacts it produced.

Two things pin separately from the CLI:

- **Modules.** Your app's `nsx.lock` records the exact revision of every module
  resolved into it. Commit it. See
  [Lock and sync](/neuralspotx/guides/modules/lock-and-sync/).
- **The SDK.** The provider module's pinned revision determines which AmbiqSuite
  drop you build against. See
  [SDK foundation and overrides](/neuralspotx/guides/modules/sdk-providers/).

## Verifying what you installed

Each GitHub release carries the wheel, the source distribution and a
`SHA256SUMS` manifest covering both. The same files are on PyPI, byte for byte.

Ask the installed CLI for its distribution version:

```bash
nsx --version
```

or `uv tool list` if you installed it as a tool, `pipx list` if you used pipx.
