---
title: Guides
description: Task guides for building apps with NSX — modules, memory, startup, toolchains and the concepts behind app generation.
---

The guides cover the work that happens after your first app builds: declaring and pinning
module dependencies, deciding what goes in which memory region, understanding what the
generated startup and linker files do, and choosing a toolchain for a target.

They also carry the concepts an app author eventually needs: how NSX generates an app, how
it resolves a dependency graph, what a module and its metadata actually are, and how one
app targets several boards. Everything NSX generates is ordinary CMake and Ninja, so these
pages explain the generated project rather than hiding it.

:::note[This section is still being filled in]
The user guide, the architecture concepts and the examples are being reorganised and moved
here in [#260](https://github.com/AmbiqAI/neuralspotx/issues/260). Until that lands, the
published site at <https://ambiqai.github.io/neuralspotx/> remains the complete
documentation.
:::
