---
title: Modules
description: What each neuralSPOT-X module provides, and which SoCs, boards and toolchains it declares compatibility with.
---

An NSX app is a thin project plus the modules it depends on. The registry pins each module
to a project and a revision, and every module ships a manifest declaring its type, what it
provides, what it depends on, and which boards, SoCs and toolchains it is compatible with.
`nsx module list` and `nsx module describe` read exactly that data.

Compatibility here is declared in a module's manifest, not proven on hardware. Treat it as
the author's statement of intent and validate on your own target before you rely on it.

:::note[This section is still being filled in]
The generated module catalog, the per-module pages and the board matrix are being built in
[#259](https://github.com/AmbiqAI/neuralspotx/issues/259) from the registry lock and the
module manifests, so the pages cannot drift from what `nsx` reports. Until that lands,
`nsx module list --registry-only` reports the same data.
:::
