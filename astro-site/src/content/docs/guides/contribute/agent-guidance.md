---
title: Agent guidance
description: What an agent working in an NSX app should rely on, which surfaces are machine readable, and the invariants not to break.
---

NSX is built to be driven by tools as well as by people. This page is what an agent
working on an NSX app, or on NSX itself, should know before it starts writing.

## Read structured output, not help text

Three surfaces are machine readable and stable enough to build on:

- `nsx commands --json` returns the whole command tree: every command and subcommand,
  which are aliases, and each one's options with flags, defaults and help strings. It
  replaces walking `--help`.
- `nsx doctor --json` returns `{ok, checks[], notes}`, each check carrying `label`, `ok`,
  `required`, `detail` and `hint`. Enough to decide whether a build can be attempted.
- The module catalog is published as data at
  [`/neuralspotx/modules/catalog.json`](/neuralspotx/modules/catalog.json), and
  `nsx module list`, `nsx module describe`, `nsx module validate` and `nsx outdated` all
  take `--json`.

For anything beyond inspection, import the Python API rather than shelling out: you get
typed results and a single `NSXError` hierarchy instead of exit codes and prose. See the
[Python API guide](/neuralspotx/guides/python-api/).

## Find modules by what they do

Module manifests carry `summary`, `capabilities`, `use_cases`, `anti_use_cases`,
`agent_keywords`, `example_refs` and `composition_hints` precisely so that a module can be
selected without reading its source. `nsx module search` matches across all of them.

`anti_use_cases` is the field that saves the most time. It rules a module out, which is
usually the faster half of the decision.

## Respect the generated boundary

Some of an app is yours to edit and some is regenerated. Writing to the wrong half
produces work that disappears at the next `nsx configure`.

| Edit | Do not edit |
| --- | --- |
| `nsx.yml`, `src/`, `CMakeLists.txt` | `cmake/nsx/`, `boards/`, `modules/`, `build/` |

Changing a module means changing the module, not its vendored copy. See
[Custom modules](/neuralspotx/guides/modules/custom-modules/).

## Change intent, then re-resolve

The order matters, because the lock is generated from the manifest and not the other way
round:

1. Edit `nsx.yml`, or use `nsx module add` and `nsx module remove`, which edit it for you.
2. Run `nsx lock` to re-resolve, or let `nsx configure` do it.
3. Run `nsx sync` to make `modules/` match, or let `nsx configure` do it.

Never hand-edit `nsx.lock`. It records commits and content hashes that `nsx sync --frozen`
verifies, so an edited lock is a lock that will fail its own check.

## Verify without changing

When you need to know whether a tree is consistent rather than to make it consistent:

```bash
nsx lock --check     # read-only, non-zero if the lock is stale
nsx sync --frozen    # fails on drift instead of correcting it
nsx outdated --exit-code --json
```

These are the right calls in any automated context, because they cannot silently rewrite
what they were asked to inspect.

## Do not invent capability claims

Everything NSX says about which boards, SoCs and toolchains a module supports comes from
that module's own manifest. It is a declaration by its author, not a record of a hardware
run. The same is true of an example's `status` and `boards_tested` front matter.

When summarizing for a user, carry the distinction through: say declared compatible, not
validated or supported. If you cannot find a source of record for a claim, leave it out
rather than filling the gap.

The same applies to anything numeric about silicon. Power figures, memory sizes and clock
speeds belong to a datasheet or to a file in the repository, and a page here that quotes
one names the file it came from.

## Working on NSX itself

The repository's own `AGENTS.md` is the canonical instruction set for changing NSX:
architectural choices, working rules, environment escape hatches, schema versioning and
the regressions to avoid. Read it before changing behavior rather than inferring the rules
from the surrounding code.

Two things from it are worth repeating here because they shape how a change is reviewed:
NSX is the single source of truth for app generation and module metadata, and schema
changes are deliberate, versioned events rather than silent additions.
