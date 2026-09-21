---
title: Concepts
description: The five ideas behind how NSX generates an app, resolves its dependencies and keeps one source tree building for several boards.
---

You can use NSX without reading any of this. These pages are for when something behaves in
a way you did not expect and you want to know why, or when you are deciding how to
structure work that NSX will have to live with for a while.

Five ideas carry most of it.

**Everything is generated, nothing is hidden.** NSX writes an ordinary CMake and Ninja
project and then gets out of the way. There is no build wrapper interpreting your
intentions at compile time. If you want to know what a build did, read the generated tree.
See [App generation flow](/neuralspotx/guides/concepts/app-generation-flow/).

**The app declares intent; the lock records fact.** `nsx.yml` says what you want. `nsx.lock`
says what that resolved to, down to commits and content hashes, per target board. The two
files are deliberately different documents, and every reproducibility guarantee NSX makes
rests on that split. See [Dependency model](/neuralspotx/guides/concepts/dependency-model/).

**A module is a manifest plus a CMake surface.** Not a package format, not a plugin API.
A module says what it is, what it needs and what it declares compatibility with, and it
exports CMake targets. Anything that does those two things is a module, including one you
write this afternoon. See [Module model](/neuralspotx/guides/concepts/module-model/).

**Metadata is explicit and typed.** Four schemas describe apps, modules, boards and locks.
NSX validates against them rather than inferring, which is why a bad manifest fails at
resolution with a field name instead of failing at link time with a missing symbol. See
[Metadata model](/neuralspotx/guides/concepts/metadata-model/).

**A target is a first-class thing, not a build flag.** One app can declare several boards,
and each gets its own resolved module set and its own build directory. Portability is
something the model supports rather than something you achieve with preprocessor
conditionals. See [Multi-target and portability](/neuralspotx/guides/concepts/multi-target/).

## Where these pages stop

They describe how NSX behaves, not why it was designed that way or where it is going.
Field-by-field tables live in the generated
[configuration reference](/neuralspotx/reference/config/); command options live in the
generated [CLI reference](/neuralspotx/reference/cli/); the modules themselves are in the
[catalog](/neuralspotx/modules/catalog/).
