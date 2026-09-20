---
title: Dependency model
description: How NSX turns the modules you declare into the set it actually builds, what the board baseline contributes, and why the closure lives only in the lock.
---

An app declares a short list of modules. It builds a much longer one. This page is about
what happens in between.

## Three inputs

The resolved set comes from three places:

1. **The board's baseline.** Choosing a board implies a starter profile: the SoC HAL, the
   BSP, the CMSIS startup pieces and the runtime core. None of it appears in your
   `modules:` list because you did not choose it. `baseline: none` in `nsx.yml` opts out
   entirely.
2. **Your direct declarations.** The `modules:` list in `nsx.yml`, layered additively on
   top of the baseline.
3. **What those need.** Each module's own manifest declares `depends.required`, and
   resolution follows those edges until nothing new appears.

## Required is resolved, optional is not

Module manifests can declare `depends.optional` as well as `depends.required`. Only
required dependencies are traversed. Optional ones are documentation: they are searchable,
they appear on the module's catalog page, and they tell you what a module is designed to
work alongside. Nothing installs them.

This is worth knowing because a module can look like it should have pulled something in
and not have done. If you want an optional dependency, declare it yourself.

## The closure lives only in the lock

`nsx.yml` never grows to include transitive dependencies. It stays the list of things you
asked for. The full resolved set is written to `nsx.lock`, per target board.

That split is what makes the two files readable for different purposes. `nsx.yml` is a
statement of intent that you maintain and review. `nsx.lock` is a generated record you
read when you need to know exactly what a binary was built from, and it is exact: project,
kind, the constraint it resolved from, the commit, and a content hash of the tree.

A consequence people hit: `nsx module list` shows direct dependencies, so a module that is
present in `modules/` and being compiled may not appear there. That is the closure, not a
bug.

## Resolution is per board

Each board in `targets.supported` gets its own resolved section in the lock. Two boards on
different SoC families legitimately resolve different module sets and can even land on
different SDK revisions, because the registry pins an SoC family to the first SDK release
that supports it.

Resolution is therefore also where a portability problem surfaces. Adding a board and
running `nsx lock` tells you whether that board's closure can be satisfied, before any
compiler runs.

## What NSX rejects

Four rules are enforced during resolution, so all four fail at lock time rather than at
link time:

- **No cycles.** `Dependency cycle detected at module '<name>'`. Break it by moving the
  shared piece into a third module.
- **At most one SDK provider.** A module can require a specific one through
  `constraints.required_sdk_provider`; two providers in one closure is a conflict. See
  [SDK providers](/neuralspotx/guides/modules/sdk-providers/).
- **A board module depends on exactly one SoC module.** A board that claims two SoCs is
  not a board.
- **Declared compatibility must hold.** A module whose `compatibility.boards`,
  `compatibility.socs` or `compatibility.toolchains` excludes your target is rejected
  rather than built.

## When resolution cannot run

The manifests that describe the graph live in the module repositories, so resolution needs
to reach them:

```text
Unable to resolve dependency metadata for nsx.yml modules [nsx-audio]: ...
Run `nsx lock` with the required module sources available so nsx.lock can record the
full dependency closure.
```

In practice that is a network failure, a private repository, or a revision that has gone
away upstream. If a module's remote is unreachable during a re-lock, NSX records it as
`unresolved` and keeps its last known content hash rather than dropping it from the
graph.

## Where overrides come from

Two layers of registry exist. NSX ships one, and an app can add its own under
`module_registry` in `nsx.yml`. The app's entries win, and a module-level entry is more
specific than a project-level one.

That precedence is how you test a fork without changing NSX, and it travels with the app:
anyone who clones your repository resolves through your overrides too. See
[Custom modules](/neuralspotx/guides/modules/custom-modules/).
