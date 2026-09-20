---
title: Releases and versioning
description: How NSX versions are numbered and tagged, what the Provisional stability tier means, and how to pin a version you depend on.
---

NSX is published to PyPI as `neuralspotx`. Every release is cut from `main` by an
automated workflow, so what you install is always a commit that passed CI as it
stands, not a branch snapshot.

## Cadence

There is no release calendar. Changes accumulate on `main` into a pending
release pull request, and a release happens when a maintainer merges it. Expect
releases in batches rather than on a fixed day, and expect fixes to reach PyPI
within days rather than weeks.

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
reused, so a tag you pin today points at the same commit indefinitely. Tags
older than `neuralspotx-v0.7.9` may be lightweight or use a bare `v0.6.3` form;
those stay as they are and are not rewritten.

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

## How to pin

Pin an exact version anywhere NSX is a dependency of something you ship or
automate.

```bash
# One-off tool install
pipx install neuralspotx==0.8.1

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
  [SDK providers](/neuralspotx/guides/modules/sdk-providers/).

## Verifying what you installed

Each GitHub release carries the wheel, the source distribution and a
`SHA256SUMS` manifest covering both. The same files are on PyPI, byte for byte.

The `nsx` command does not print its own version, so ask the package:

```bash
python -c "import importlib.metadata as m; print(m.version('neuralspotx'))"
```

or `pipx list` if you installed it as a tool.
