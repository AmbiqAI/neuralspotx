# Architecture Roadmap

## Current Stage

1. NSX CMake module layering exists inside `neuralspotx`.
2. NSX CLI supports workspace bootstrap and module lifecycle.
3. Metadata v1 exists (`nsx-module.yaml`, `registry.lock.yaml`, `nsx.yml`).

## Planned Stages

## Stage 1: Strengthen Local/Out-of-Tree Flows

1. Expand board profiles and module catalogs.
2. Improve diagnostics for compatibility and dependency failures.
3. Keep generated apps self-contained with vendored modules and board content.
4. Keep starter profiles minimal and AmbiqSuite-first for AI/profiling use cases.
5. Keep SDK provider model explicit by family (`r3`, `r4`, `r5`).

## Stage 2: Split Module Repositories

1. Move major NSX modules into separate repos.
2. Maintain stable metadata schema and package target contracts.
3. Keep `nsx create-app` flow unchanged from user perspective.
4. Use AP3 as first full decoupling target; keep AP510 regression-compatible.
5. Keep AP4 as profile/metadata scaffold until bring-up is ready.

## Stage 3: NSX CLI Packaging

1. Publish `nsx` CLI to PyPI.
2. Support `pipx` installation for global CLI usage.
3. Keep per-project deterministic environment options (`uv`/venv).

## Stage 4: Tool Ecosystem Migration

1. Build higher-level tools (for example profiling/autodeploy-like tooling) on
   top of NSX app/module generation APIs.
2. Retire dependencies on legacy root monorepo tooling paths.

## Non-Goals

1. NSX will not try to be a universal board-abstraction layer like Zephyr.
2. Zephyr-only module ingestion is not a goal for NSX module registry.
3. BLE/network/RTOS stacks are not baseline requirements for NSX starter profiles.
