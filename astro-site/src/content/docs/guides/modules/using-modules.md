---
title: Using modules
description: Find, add, inspect and remove the modules an NSX app depends on, and understand what the board baseline already gives you.
---

A module is a reusable unit of firmware with a manifest that says what it provides, what
it needs and what it declares compatibility with. An app's `nsx.yml` lists the modules you
asked for directly. Everything else in the build arrives because something you asked for
needed it.

The [module catalog](/neuralspotx/modules/catalog/) is the full list with a page per
module. This page is about working with them from inside an app.

## You start with more than you declared

`nsx create-app` records the board, and the board's starter profile is layered in as an
implicit baseline: the SoC HAL, the BSP, the CMSIS startup pieces and the runtime core.
None of that appears in your `modules:` list, because it is not something you chose. It is
what building for that board means.

Your declarations are additive on top of that baseline. If you want the baseline gone
entirely, `nsx.yml` accepts one opt-out:

```yaml
baseline: none
```

That is what `--no-bootstrap` writes. With it the app depends on exactly what you list and
nothing else, which is a reasonable starting point for a bring-up and a poor one for a
first app.

## Seeing what you have

```bash
nsx module list              # what this app depends on
nsx module list --json       # the same, machine readable
nsx module list --registry-only   # every module NSX knows about
```

`nsx list-modules` is an alias for the same command.

`nsx module describe <name>` prints one module's manifest in full: its type, version,
what it provides, its dependencies, and the boards, SoCs and toolchains it declares
compatibility with. `--json` gives the same content as data.

`nsx module search <query>` matches across names, summaries, capabilities, use cases and
the author's own keywords, so it finds modules by what they do rather than by what they
are called.

## Adding a module

```bash
nsx module add nsx-uart
```

`nsx add` is an alias. The command appends the module to `nsx.yml`, then re-resolves and
syncs, so `modules/` and `nsx.lock` both catch up.

Two refusals are common and both mean what they say:

```text
Module 'nsx-uart' is already a direct dependency in nsx.yml
```

```text
--board apollo4p_evb not in the app's supported targets (apollo510_evb)
```

`--dry-run` shows the changes without writing them.

### Scoping a module to one board

`--board` is repeatable and restricts the dependency to the boards you name:

```bash
nsx module add nsx-ble --board apollo4p_blue_kxr_evb --board apollo510b_evb
```

In `nsx.yml` that becomes an entry with a `boards` list. Boards outside the list resolve
without it, which is how one manifest serves targets with different radios or peripherals.
An entry with no `boards` applies to every target.

## Removing a module

```bash
nsx module remove nsx-uart
```

This removes your direct declaration. If another module in the graph still requires it,
it stays in the closure and keeps building, which is correct: you stopped asking for it,
but something else still needs it. `nsx module list` shows direct dependencies, so the
module disappearing from that list while remaining in `modules/` is expected.

## Keeping up with upstream

```bash
nsx outdated            # which git-backed modules lag their upstream tip
nsx module update       # re-resolve and re-vendor
```

`nsx outdated` only has something to say about modules backed by a git constraint, because
a packaged or vendored module has no upstream tip to compare against. `--json` reports
`checked`, `skipped` and `outdated_count`, and `--exit-code` makes it fail a CI job.

[Lock and sync](/neuralspotx/guides/modules/lock-and-sync/) covers the resolution and
pinning behind all of this, including how to pin a module to an exact revision.

## Optional dependencies are information, not installs

Module manifests can declare `depends.optional` alongside `depends.required`. NSX resolves
required dependencies into the closure. Optional ones are metadata: they are searchable
and shown on the module's catalog page, and they tell you what a module can work with, but
nothing pulls them in. If you want an optional dependency in your build, add it yourself.

## Where modules come from

| Source | What it means | How you get it |
| --- | --- | --- |
| Registry | A module NSX pins in its packaged registry, fetched from git or shipped inside the wheel. | The default. `nsx module add <name>`. |
| Local path | A module you are developing, on disk outside the app. NSX mirrors it into `modules/` on every sync. | `nsx module add <name> --local --path <dir>` |
| Vendored | A module whose sources live in your repository. `nsx sync` leaves it alone. | `nsx module add <name> --vendored` |

An app can also override where the registry points for a given module, which is how you
test a fork without touching NSX itself.
[Custom modules](/neuralspotx/guides/modules/custom-modules/) covers all three cases and
how to write a module of your own.

## Compatibility is declared

A module's `compatibility.boards`, `compatibility.socs` and `compatibility.toolchains`
come from the manifest its author wrote. NSX enforces them, so an incompatible combination
is rejected rather than silently built, but enforcement is against the declaration. It is
not evidence that the module was run on that board.
