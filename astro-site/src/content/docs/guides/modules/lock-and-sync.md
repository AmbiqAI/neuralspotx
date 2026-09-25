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

### What a local source contributes

A `local` module's source is a directory you named with `source.path`, or a project
registered with `--project-local-path`. What NSX hashes and mirrors from it depends on
whether that directory is the top level of a git work tree:

- **A git work tree top level** contributes the files
  `git ls-files --cached --others --exclude-standard` lists: tracked files, including
  uncommitted edits, plus untracked files that are not ignored. Anything your `.gitignore`
  excludes, such as build output and generated artifacts, is neither hashed nor copied.
  Initialized submodules and nested repositories inside it are listed the same way;
  an uninitialized submodule contributes nothing.
- **Any other directory**, including a subdirectory of a repository, contributes every
  file under it except `.git`, `__pycache__`, `.pytest_cache`, `.DS_Store`, `.venv` and
  `venv`.

`nsx sync` makes `modules/<project>/` hold exactly those files, and deletes mirrored files
the source no longer lists. Because ignored files never enter the hash, rebuilding
artifacts inside the source does not make the lock drift.

The app may live inside its own local source, for example under the source's ignored
`build/` directory, as long as the source's git ignores the app directory. If git would
list the app, NSX leaves the module unmirrored rather than copy the source into itself.

:::caution[One-time hash change for git-backed local sources]
NSX 0.8.1 and earlier hashed every file under a local source, ignored ones included. If
your local source is a git work tree with ignored files in it, its `content_hash` changes
once after upgrading, and `nsx sync --frozen` reports drift. Run `nsx lock` once, commit
the new `nsx.lock`, and `--frozen` passes again.
:::

Because resolution happens per board, two targets on different SoC families can legitimately
land on different module sets in the same lock file. The full schema is on the generated
[`nsx.lock` reference](/neuralspotx/reference/config/nsx-lock/).

## Pinning a module

By default a module resolves to whatever revision NSX's registry pins for it. To hold one
module somewhere else, give the entry a revision in `nsx.yml`:

```yaml
modules:
  - name: nsx-audio
    revision: v0.4.1
```

`revision` accepts a tag, a branch or a commit. NSX resolves it through the remote at lock
time and records the commit it landed on, so the lock is exact even when the constraint is
not:

- A **commit** is already exact. It resolves to itself and never moves.
- A **tag** is exact in practice. It resolves to the commit the tag points at, and it is
  recorded alongside the commit so the lock says which tag you asked for.
- A **branch** is a moving constraint. It resolves to the tip at lock time, and re-running
  `nsx lock --update` moves it. Between updates the lock still pins a single commit, so
  the build does not shift underneath you.

Pin a branch only when you are tracking something you also control. `nsx outdated` is the
tool for noticing that a pinned module has fallen behind, rather than a floating ref that
moves without telling you.

:::caution[A git source in a module entry is rejected]
`nsx.yml` parses a `source.git` block, but the resolver does not accept one:

```text
nsx.yml: module 'my-sensor' uses a git source, which is not yet supported by the
resolver. Use a registry, path, or vendored source for now.
```

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
nsx sync --frozen         # fail if modules/ does not match the lock
nsx outdated --exit-code  # fail if a git module lags its upstream
```

`nsx lock --check` is read-only. It prints what would change and exits non-zero if
anything would, which catches an `nsx.yml` edit that was never locked.

`nsx sync --frozen` refuses to correct. Every form of drift becomes an error naming the
module:

```text
Vendored module 'my-sensor' content drifted from lock ...
Local source for 'my-sensor' at /home/you/src/my-sensor has drifted ...
```

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
nsx lock --update                   # re-resolve everything to upstream tip
nsx lock --update --module nsx-audio  # re-resolve one module
nsx update                          # re-resolve and sync in one step
```

`nsx outdated` only reports on git-backed modules, because a packaged or vendored module
has no upstream tip to compare against. It tells you which modules it skipped and why, and
`--json` gives `checked`, `skipped` and `outdated_count` for a script.

`nsx update` is `lock --update` followed by `sync`. It prompts before changing the lock
unless you pass `--yes`.

Review the diff to `nsx.lock` before committing an update. It is the only record of what
your firmware is built from.

## When upstream is unreachable

If a module's remote cannot be reached during a lock, NSX records the module as
`unresolved` and keeps the last known content hash rather than dropping it. The app still
builds from what is on disk, and the lock says plainly that the entry was not confirmed
against upstream. Re-run `nsx lock` with network access to resolve it properly.
