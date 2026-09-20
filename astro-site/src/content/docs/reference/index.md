---
title: Reference
description: Every NSX command and option, the public Python API, and the schema of each manifest NSX reads.
---

Reference is the lookup section: what a command accepts, what a function returns, and what
a manifest field means. It is generated from the source rather than written by hand, so it
describes the version of NSX you installed and not a snapshot of it.

Three surfaces live here. The CLI, where every top-level command and subcommand is
documented with its options and defaults, and many commands also support `--json` for
scripting. The public Python API, the names exported from `neuralspotx`, all of which are
currently marked Provisional. And the configuration schemas for `nsx.yml`,
`nsx-module.yaml`, `board.yaml` and the registry lock.

:::note[This section is still being filled in]
The generated CLI pages, the Python API reference and the configuration schemas are being
built in [#258](https://github.com/AmbiqAI/neuralspotx/issues/258), with completeness
checks so no command or exported name can go missing. Until that lands, run `nsx <command>
--help` or see the published site at <https://ambiqai.github.io/neuralspotx/>.
:::
