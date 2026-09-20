---
title: Adding a module
description: Take a module from a scaffold to something other apps can depend on, including the metadata that makes it findable and the rules NSX enforces.
---

[Custom modules](/neuralspotx/guides/modules/custom-modules/) covers using a module of
your own in one app. This page is about making one that other apps and other people can
depend on.

The difference is mostly discipline: the same manifest, held to a higher standard, because
you are no longer the only reader.

## The workflow

1. **Scaffold.** `nsx module init my-sensor --type algorithm` writes the manifest, the
   CMake, a header and a source stub.
2. **Write the manifest properly.** Identity, dependencies, and compatibility you have
   actually built. See below.
3. **Expose a CMake surface.** A package and one or more targets, with honest public
   include directories and link dependencies.
4. **Validate.** `nsx module validate ./my-sensor`, and `--json` if something else is
   consuming the result.
5. **Prove it in an app.** Generate an app, add the module with `nsx module register`, and
   build it for every board the manifest claims. This is the step that turns a
   compatibility list from a hope into a statement.
6. **Publish it** as a repository other apps can register against, or propose it for the
   NSX registry.

## Design rules

**Keep compatibility explicit.** `compatibility.boards`, `compatibility.socs` and
`compatibility.toolchains` are enforced at resolution, so they are load bearing. Declaring
`*` for all three passes every check and tells nobody anything, and it makes your catalog
page actively misleading.

**Keep the dependency closure clean.** Every entry in `depends.required` is vendored into
every app that uses you. Depend on what you need to compile and link, and nothing else.
Remember that `depends.optional` is documentation only: nothing resolves it, so a module
that needs something must require it.

**Depend on wrappers, not on the SDK.** A module that talks to the HAL or BSP wrapper
ports to any part that has one. A module that includes vendor SDK headers directly is
bound to that SDK. See [SDK providers](/neuralspotx/guides/modules/sdk-providers/).

**Avoid pass-through wrappers.** A module that only forwards another module's interface
adds a name, a manifest and a resolution step, and no capability. If your module would be
a thin forward, contribute to the module underneath instead.

**Pick the type that describes it.** The eight types are not decorative: NSX enforces the
one-SDK-provider rule and the board-to-SoC rule from them, and the catalog groups by them.
See [Module model](/neuralspotx/guides/concepts/module-model/).

## The metadata that decides whether anyone finds you

Seven optional fields exist so a person or an agent can pick your module without reading
its source. Treat them as required:

| Field | What to put in it |
| --- | --- |
| `summary` | One line. What it does, not what it is built on. |
| `capabilities` | The short tags the catalog filters by. |
| `use_cases` | Concrete situations where this is the right choice. |
| `anti_use_cases` | Situations where it is the wrong one. |
| `agent_keywords` | The words someone would search for who does not know your naming. |
| `example_refs` | Apps or examples that use it. |
| `composition_hints` | What it is normally combined with. |

`nsx module search` matches across all of them. A module with none is discoverable only by
someone who already knows its name, which defeats the point of publishing it.

## What NSX will reject

- A dependency cycle, reported at resolution as
  `Dependency cycle detected at module '<name>'`.
- A second SDK provider in one app's closure.
- A board module that depends on more than one SoC module.
- A manifest whose schema version NSX does not recognize.
- A module whose declared compatibility excludes the app's target.

All five fail at `nsx lock`, with a module name, rather than at link time.

## Versioning

`module.version` is a semantic version, and apps can pin to a tag through a `revision`
constraint. That means your tags are an interface: once an app pins `v0.3.0`, the tree at
that tag is what it builds, and moving the tag changes somebody's firmware without
changing their manifest. Cut a new tag instead.

See [Lock and sync](/neuralspotx/guides/modules/lock-and-sync/) for how a constraint
becomes a pinned commit.

## Getting it into the NSX registry

A registry entry makes a module available to every app by name, and it is a change to the
NSX repository: the registry entry, its revision pin, and the tests that cover it. Start
with an issue on
[AmbiqAI/neuralspotx](https://github.com/AmbiqAI/neuralspotx/issues); the repository's
`CONTRIBUTING.md` covers development setup and the review process.
