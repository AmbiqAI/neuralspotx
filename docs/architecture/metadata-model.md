# Metadata Model

NSX uses three metadata layers.

## 1. Module Metadata: `nsx-module.yaml`

Owned by each module repo.

Declares:

1. module identity, type, and version
2. backend support flags
3. CMake package and target contract
4. required and optional module dependencies
5. compatibility constraints for board, SoC, and toolchain

## 2. Curated Lock Metadata: `neuralspotx.data/registry.lock.yaml`

Owned by the NSX tooling repo.

Declares:

1. channels such as `stable` and `preview`
2. known module entries and project mapping
3. starter profiles per board
4. default SDK provider revisions for supported boards

## 3. App Metadata: `nsx.yml`

Owned by each generated app.

Declares:

1. project name
2. target board and SoC
3. toolchain, channel, and profile
4. enabled modules and revisions
5. optional app-local module registry overrides

## Resolution Order

1. load the curated lock registry
2. merge app-local `module_registry` overrides
3. resolve the requested module and required dependency closure
4. validate compatibility against the app target
5. materialize source content from curated module locations
6. copy or replace vendored `modules/` and `boards/` content inside the app
7. update `nsx.yml` and generated `cmake/nsx/modules.cmake`

The metadata model drives orchestration. CMake remains authoritative for the
actual build graph.
