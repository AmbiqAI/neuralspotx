---
title: Module model
description: What a module is in NSX terms, the eight module types, how a module contributes CMake targets, and what makes one portable.
---

A module is two things: a manifest that describes it and a CMake surface that builds it.
There is no plugin API, no registration call and no NSX-specific build language. A
directory with an `nsx-module.yaml` and a `CMakeLists.txt` is a module.

That is deliberately low. It means a module you write for your own hardware is the same
kind of object as the ones NSX ships, resolved the same way and subject to the same
checks.

## The manifest

`nsx-module.yaml` declares identity (`name`, `type`, `version`), backend support, the
CMake contract, dependencies, and the boards, SoCs and toolchains the module claims to
work with. Every field is on the generated
[`nsx-module.yaml` reference](/neuralspotx/reference/config/nsx-module-yaml/).

Two parts of it do most of the work.

**The CMake contract.** `build.cmake.package` and `build.cmake.targets` are how the rest
of the graph reaches your code. The package name is the module name with hyphens turned
into underscores, and the conventional target is that name under the `nsx::` namespace
with an `nsx_` prefix dropped if present: `nsx-timer` becomes package `nsx_timer` and
target `nsx::timer`, while `my-sensor` becomes `my_sensor` and `nsx::my_sensor`.

**The compatibility block.** `compatibility.boards`, `compatibility.socs` and
`compatibility.toolchains` are enforced at resolution. They are also the only thing
telling a reader where a module is expected to work, which makes declaring `*` for all
three worse than useless: it passes every check and tells nobody anything.

## The eight types

| Type | What it is |
| --- | --- |
| `sdk_provider` | Supplies a vendor SDK payload. An app resolves at most one. |
| `soc` | Describes an SoC. A board module depends on exactly one. |
| `board` | Describes a board: its SoC, BSP wiring, memory and debug fragments. |
| `runtime` | A runtime or execution layer the app runs on top of. |
| `portable_api` | An interface other modules implement or consume, independent of the part. |
| `algorithm` | Signal processing, inference or other computation. |
| `backend_specific` | An implementation bound to one backend or accelerator. |
| `tooling` | Host-side or build-time tooling rather than firmware. |

The type is not decorative. NSX enforces the provider rule and the board-to-SoC rule from
it, and the [catalog](/neuralspotx/modules/catalog/) groups and filters by it. Pick the one
that describes what the module is, not the one that sounds most important.

## Layers, not a hierarchy

Modules stack in a rough order: the SDK provider at the bottom, HAL and BSP wrappers over
it, portable interfaces over those, then runtimes, algorithms and the app. Nothing in NSX
enforces that stack; it falls out of what each module declares it depends on.

What it means in practice is a portability rule. A module that depends on a wrapper module
is portable across any part that has a wrapper. A module that reaches past the wrapper into
the SDK is bound to that SDK. The wrapper's interface is something NSX controls; the SDK
underneath it is not. See
[SDK providers](/neuralspotx/guides/modules/sdk-providers/).

## Backends

Manifests declare support per backend: AmbiqSuite support is required, and Zephyr support
is declared separately and may be absent. A module that supports only a backend NSX does
not build for is not a module NSX can resolve.

## The metadata that makes a module findable

Seven optional fields exist purely so that a person or an agent can find the right module
without reading its source: `summary`, `capabilities`, `use_cases`, `anti_use_cases`,
`agent_keywords`, `example_refs` and `composition_hints`.

`nsx module search` matches across all of them, and the catalog page renders them. They
are optional in the schema and effectively mandatory in practice: a module with none of
them is discoverable only by someone who already knows its name.

`anti_use_cases` is the one worth arguing for. Saying what a module is wrong for rules it
out quickly, which is more valuable than another sentence about what it is right for.

## Writing one

[Custom modules](/neuralspotx/guides/modules/custom-modules/) is the practical guide:
scaffolding with `nsx module init`, validating with `nsx module validate`, and the three
ways to point an app at a module NSX does not pin.
