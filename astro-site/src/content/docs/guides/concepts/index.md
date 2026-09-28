---
title: Architecture concepts
description: How NSX generates applications, resolves modules, records dependencies and supports multiple targets.
---

These pages explain the structures behind the [task guides](/neuralspotx/guides/).
Read the topic relevant to a design decision or a behavior you need to understand.

## Application generation

NSX writes CMake files and an application scaffold. Your application sources remain
editable; generated support files may be replaced by later commands.
[App generation flow](/neuralspotx/guides/concepts/app-generation-flow/) explains what
is written at each stage and where ownership changes.

## Dependency resolution

`nsx.yml` declares the application's dependencies. `nsx.lock` records resolved sources,
revisions and hashes for each target. The [dependency model](/neuralspotx/guides/concepts/dependency-model/)
explains required and optional dependencies, resolution order and overrides.

## Module contracts

Modules describe their dependencies and compatibility in `nsx-module.yaml` and expose
CMake targets. The [module model](/neuralspotx/guides/concepts/module-model/) explains
module types, interfaces and backend integration.

## Configuration and metadata

Applications, modules, boards and locks have separate schemas. The
[metadata model](/neuralspotx/guides/concepts/metadata-model/) explains how these
documents relate, which ones to edit and how overrides take precedence.

## Multiple targets

An application can declare several boards, each with its own build directory and resolved
dependency set. [Multi-target and portability](/neuralspotx/guides/concepts/multi-target/)
covers shared sources, target-specific overlays and the limits of portability.

## Reference material

Use the [configuration reference](/neuralspotx/reference/config/) for field definitions,
the [CLI reference](/neuralspotx/reference/cli/) for command options and the
[module catalog](/neuralspotx/modules/catalog/) for packaged capabilities.
