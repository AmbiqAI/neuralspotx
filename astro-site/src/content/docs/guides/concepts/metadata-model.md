---
title: Metadata model
description: The four schemas NSX reads and writes, who owns each one, and how they fit together.
---

NSX validates typed metadata rather than inferring from directory layout. Four documents
carry it, each owned by someone different. Field-by-field tables for all four are
generated from the validators and live in the
[configuration reference](/neuralspotx/reference/config/); this page is about what each one
is for and how they relate.

## The four documents

| Document | Owned by | Says |
| --- | --- | --- |
| [`nsx.yml`](/neuralspotx/reference/config/nsx-yml/) | You | What this app targets and what it depends on directly. |
| [`nsx-module.yaml`](/neuralspotx/reference/config/nsx-module-yaml/) | The module's author | What a module is, needs and claims compatibility with. |
| [`board.yaml`](/neuralspotx/reference/config/board-yaml/) | The board's author | What a board is: its SoC, CPU, ABI, SDK provider and declared toolchains. |
| [`nsx.lock`](/neuralspotx/reference/config/nsx-lock/) | NSX | What the declarations above actually resolved to. |

A fifth document exists but is not yours to edit: NSX's packaged registry, which pins
every module it knows about to a project and a revision, and records which SDK revision
each SoC family uses. You can override parts of it per app, from `nsx.yml`.

## How they fit together

Resolution reads three of them and writes the fourth.

`nsx.yml` names a board. The board's `board.yaml` supplies the SoC, the CPU and ABI flags,
the SDK provider and the toolchains it declares. The board's starter profile contributes a
baseline module set, and your `modules:` list adds to it. Each module's
`nsx-module.yaml` declares what it needs, which pulls in more modules, until the graph
closes. The result is written per target board into `nsx.lock`.

So the direction of information is one way: declarations flow in, a resolved record flows
out. Nothing edits `nsx.yml` to record what resolution found, and nothing reads `nsx.lock`
to decide what the app depends on.

## Intent and fact are separate documents

This is the distinction the whole model rests on.

`nsx.yml` is intent. It is short, hand-maintained, and reviewable in a pull request. It
says `nsx-audio`, perhaps with a revision constraint, and stops there.

`nsx.lock` is fact. It is generated, long, and exact: for each target board, every module
in the closure with its project, its kind, the constraint it resolved from, the commit it
landed on and a content hash of the tree. It also records the NSX version that wrote it
and a hash of the `nsx.yml` it read.

That last pair is what makes drift detectable. `nsx lock --check` compares the manifest
hash and tells you the lock is stale without writing anything; `nsx sync --frozen`
compares content hashes and tells you the tree is stale without correcting it. See
[Lock and sync](/neuralspotx/guides/modules/lock-and-sync/).

## Per-target, not per-app

`nsx.lock` is keyed by board. Each target gets its own `target`, its own module set and
its own resolved revisions, in one file.

That is not a formality. Two boards on different SoC families can legitimately resolve
different SDK revisions, because a part is supported from the first SDK release that ships
it. A single flat lock could not express that. See
[Multi-target and portability](/neuralspotx/guides/concepts/multi-target/).

## Overrides and precedence

An app can carry its own registry entries under `module_registry` in `nsx.yml`, keyed
either by project or by module. Two precedence rules apply:

- App-local entries beat NSX's packaged registry.
- A module-level entry beats a project-level one, because it is more specific.

The override lives in your manifest, so it travels with the app. Anyone who clones the
repository resolves through the same override, which is the point.

:::caution[Overrides are invisible to the catalog]
The [module catalog](/neuralspotx/modules/catalog/) renders NSX's registry. It does not
know about your app's overrides. Inside an app, `nsx module describe <name>` is the
accurate answer.
:::

## Schema versions

Each document carries a `schema_version`, and NSX refuses one it does not recognize rather
than guessing. An upgrade that changes a schema is therefore a visible, diagnosable event
instead of a field being silently ignored.

## What to commit

Commit `nsx.yml` and `nsx.lock`. Together they are the complete description of what your
firmware is built from. `modules/` is reconstructible from the lock, which is why the
generated `modules/.gitignore` leaves it out.
