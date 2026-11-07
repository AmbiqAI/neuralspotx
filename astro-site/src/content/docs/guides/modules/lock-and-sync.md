---
title: Lock and sync
description: How nsx lock resolves and pins the module graph, how nsx sync materializes it, how to pin a module to an exact revision, and the flags that make a build reproducible in CI.
---

Two commands sit under everything else. `nsx lock` decides what the app depends on and
writes it down. `nsx sync` makes `modules/` match what was written down. Keeping them
separate is what lets a build be checked without being changed.

`nsx configure` runs both for you: it locks if there is no `nsx.lock`, then syncs. You only
reach for them directly when you want one without the other, which is most of the time in
CI.

## What `nsx lock` writes

`nsx lock` walks the graph from the board's baseline plus your declared modules, resolves
every dependency, and records the result per target board in `nsx.lock`.

Each module gets a `project`, a `kind`, the `constraint` it was resolved from, and a
`resolved` block. For a git-backed module that block carries the URL, the tag, the exact
commit and a content hash of the tree at that commit. The lock also records the NSX
version that wrote it and a hash of the `nsx.yml` it read, which is how drift is detected
later.

Five kinds appear, and they differ in where the content comes from:

| Kind | Source of truth | Re-fetched by sync |
| --- | --- | --- |
| `git` | A repository at a resolved commit | Yes |
| `packaged` | A source tree shipped inside the NSX package | Yes |
| `local` | An external directory you named with `source.path` | Yes, mirrored |
| `vendored` | `modules/<name>/` in your own repository | No |
| `unresolved` | Last known content, when upstream could not be reached | No, hash verified |

Because resolution happens per board, two targets on different SoC families can legitimately
land on different module sets in the same lock file. The full schema is on the generated
[`nsx.lock` reference](/neuralspotx/reference/config/nsx-lock/).

## Pinning a module

By default a module uses its packaged registry revision. To override a project's
revision in `nsx.yml`, use the registry override (this applies to its modules):

```yaml
module_registry:
  projects:
    nsx-ambiq-sdk:
      revision: v5.2.28
```

For a module-specific override, use `module_registry.modules.<module>.revision`.
A `revision` field directly under the app's top-level `modules` entries does not
set the effective registry revision. Check the resulting constraints in `nsx.lock`.

`revision` accepts a tag, branch or full 40-character commit SHA. Git-backed lock
entries record exact commits even when their constraints can move:

- A **full commit SHA** resolves to itself.
- A **tag** records both the tag and its resolved commit. Matching previous tag
  resolutions can be reused. If upstream moves a tag, an explicit update may change
  its resolved commit; a committed lock remains the reproducibility anchor.
- A **branch** can resolve differently on subsequent `nsx lock` writes. Normal
  locking uses the resolve-ref cache (default TTL: 300 seconds); `--update` clears
  that cache. Re-resolution does not necessarily mean a fresh network lookup.

### Unpinned Git diagnostics

Each resolved board lock warns about Git constraints that are neither full SHAs nor
recorded tags, grouping modules by project, source and revision. The warning also
appears during `nsx lock --check`; it does not fail the command or imply that a
recorded commit has changed. To stabilize future resolution, set an explicit tag
or full commit SHA in the registry override above, then review the new lock.

Packaged, local and vendored entries are excluded. In particular, the packaged
`neuralspotx@main` registry self-reference represents bytes from the installed tool,
recorded as `kind: packaged`, rather than a remotely resolved branch. This is based
on source kind, not a generic warning exemption for a project name. Unresolved
sources retain their separate fallback warnings; they do not have exact commits.

These diagnostics use the `neuralspotx` logger (stderr in the CLI, suppressed by
normal `-q` filtering). API callers capture them with a logging handler, not the
`emit=` callback. API `quiet=True` suppresses summaries, not warnings. The separate
age-based stale-lock warning and its settings are unchanged.

:::caution[A git source in a module entry is rejected]
The project loader rejects `source.git` before resolving or downloading dependencies.
Use a registry override, `source.path`, or `source.vendored` instead.

An explicit `source` block must be a mapping. `path`, `git`, and `rev` values must be
non-empty strings; `vendored` must be a YAML boolean (`true` or `false`). Invalid values
such as `git: false`, `path: 123`, or `vendored: "true"` produce a field-specific error
instead of falling back to registry resolution. Omit `source` or use `{}` for registry
resolution. `vendored: false` also leaves registry resolution selected.

To resolve a module from a repository, register it as an app-local project instead. See
[Custom modules](/neuralspotx/guides/modules/custom-modules/).
:::

## What `nsx sync` does

`nsx sync` reads `nsx.lock` and makes `modules/` match it. It never writes the lock: if
syncing could change what you depend on, the split between the two commands would be
pointless.

It is idempotent and cheap on the second run, because it hashes what is already on disk
and skips anything that matches. `--force` re-vendors every fetchable module regardless.

## Checking without changing

Three flags turn this pair into a build check.

```bash
nsx lock --check          # report manifest and resolution drift, write nothing
nsx sync --frozen         # fail if modules/ differs from the lock; fetch only what is missing
nsx outdated --exit-code  # fail if a git module lags its upstream
```

`nsx lock --check` does not write the lock or build glue, but can use or populate
caches. It checks manifest/content consistency and exits non-zero on drift. Matching
previous Git resolutions, including branch SHAs, can be reused: a successful check
is not proof that branches match their latest upstream tips. `nsx lock --check
--update` clears the resolve cache and reconsiders previous resolutions without
writing the lock/build glue; it reports drift rather than applying it.

`nsx sync --frozen` refuses to correct. Every form of drift becomes an error naming the
module:

```text
Vendored module 'my-sensor' content drifted from lock ...
Local source for 'my-sensor' at /home/you/src/my-sensor has drifted ...
Module 'my-sensor' at modules/my-sensor does not match nsx.lock ...
```

A module that is missing, as on a fresh clone where `modules/` is gitignored, is not drift.
`--frozen` fetches it at the commit in `nsx.lock` (git modules need network access) and fails
if its content hash differs from the lock. The same holds for the `cmake/nsx` tree that ships
with neuralspotx: after upgrading neuralspotx, run `nsx lock` once before using `--frozen`.

`--frozen` is also accepted by `configure`, `build`, `flash` and `view`, where it applies
to the implicit sync those commands would otherwise perform.

:::tip[The CI recipe]
```bash
nsx lock --check
nsx sync --frozen
nsx build --frozen
```
The first proves the lock matches the manifest, the second proves the tree matches the
lock, and the third builds without either being allowed to move.
:::

## Updating on purpose

```bash
nsx outdated                        # what has moved upstream
nsx lock --update                   # clear cache and reconsider all resolutions
nsx lock --module nsx-audio         # refresh the selected project; implies --update
nsx update                          # re-resolve and sync in one step
```

`nsx outdated` only reports on git-backed modules, because a packaged or vendored module
has no upstream tip to compare against. It tells you which modules it skipped and why, and
`--json` gives `checked`, `skipped` and `outdated_count` for a script.

`nsx update` is `lock --update` followed by `sync`. Its preliminary report shows
upstream availability for the default target, **not a targeted change plan**; it
may include unselected projects. Three or more outdated modules in that report
require confirmation (or `--yes`), even for a targeted request.

`lock --module X` and `update --module X` refresh every Git module belonging to X's
registry project in each applicable target closure. Modules sharing a project share
one vendored source directory. Unrelated projects retain matching prior Git commits
and tags, including floating branches. Separate projects sharing a URL are not
selected together. Conflicting Git commits or mixed Git/unresolved rows sharing one
directory are rejected before writing the affected lock section; align revisions,
retry unreachable refs, or give separate projects distinct paths.

This preserves compatible Git resolutions, not the entire lockfile: changed project
identities, URLs or constraints resolve normally, new dependencies are added, removed
dependencies disappear, and local/vendored/packaged content is rehashed. Closure uses
the existing metadata acquisition rules, including app-local metadata precedence;
it does not discover a new remote dependency graph at the updated commit. If upstream
metadata changes, materialize it with `sync` and run `lock` again. A normal writable
`lock` refreshes floating refs; review that subsequent diff too.

Without a usable prior lock there are no resolutions to preserve. Unknown selections
fail before lock sections are written. With multiple targets, a selection need only
exist in one requested target; it applies where present. A board-restricted operation
preserves other board sections. Later failures are not an all-target transaction.
`lock --check --update --module X` uses the same selection rules without writing the
lock or build glue; cache changes are still possible.

In the Python API, `lock_app(modules=["X"])` alone does not request an update;
pass `update=True` explicitly. CLI `lock --module X` implies `--update`. None or an
empty list with `update=True` requests a full refresh. `update_app` locks all targets
and syncs the default target, retaining its existing shared-source behavior.

Review the diff to `nsx.lock` before committing an update. It is the only record of what
your firmware is built from.

## When upstream is unreachable

If a module's remote cannot be reached during a lock, NSX records the module as
`unresolved` and keeps the last known content hash rather than dropping it. The app still
builds from what is on disk, and the lock says plainly that the entry was not confirmed
against upstream. Re-run `nsx lock` with network access to resolve it properly.
