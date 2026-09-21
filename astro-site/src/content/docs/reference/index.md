---
title: Reference
description: Every NSX command and option, the public Python API, and the schema of each manifest NSX reads.
---

Reference is the lookup section: what a command accepts, what a function returns, and what
a manifest field means. It is generated from the source rather than written by hand, so it
describes the version of NSX you installed and not a snapshot of it.

## [CLI](/neuralspotx/reference/cli/)

Every top-level command and subcommand, with its options, defaults and usage, taken from
the argument parser. Many commands also support `--json` for scripting, and
`nsx commands --json` returns the whole tree at once.

## [Python API](/neuralspotx/reference/api/)

The names exported from `neuralspotx`, with their signatures, parameters and return types.
All of them are currently Provisional, which each page says once at the top.

## [Configuration](/neuralspotx/reference/config/)

The schema of `nsx.yml`, `nsx-module.yaml`, `board.yaml` and the `nsx.lock` resolution
lock: every field, its type, whether it is required and what it means.

## [Releases and versioning](/neuralspotx/reference/releases/)

How versions are numbered and tagged, what the Provisional stability tier means for
everything the Python API exports, and how to pin a version you depend on.

## Machine-readable

The same content is published for tools and agents:
[`reference.txt`](/neuralspotx/reference/reference.txt) as one text bundle,
[`reference.json`](/neuralspotx/reference/api/reference.json) as the Python model,
[`cli.json`](/neuralspotx/reference/cli.json) as the command tree, and
[`config.json`](/neuralspotx/reference/config.json) as the configuration schemas.
