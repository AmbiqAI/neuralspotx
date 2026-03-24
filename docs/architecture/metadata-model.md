# Metadata Model

NSX uses three metadata layers.

## 1) Module Metadata: `nsx-module.yaml`

Owned by each module.

Declares:

1. module identity/type/version
2. backend support (`ambiqsuite`, optional `zephyr`)
3. CMake package/targets contract
4. required/optional module dependencies
5. compatibility constraints (board/soc/toolchain)
6. optional Zephyr integration path metadata

Purpose:

- machine-checkable compatibility and dependency resolution
- backend policy enforcement before build/configure

## 2) Curated Lock Metadata: `neuralspotx.data/registry.lock.yaml`

Owned by NSX CLI.

Declares:

1. channels (`stable`, `preview`)
2. known module entries and project mapping
3. starter profiles per board
4. compatibility matrix defaults

Purpose:

- deterministic defaults
- starter profile curation
- known-good module mapping

## 3) App Metadata: `nsx.yml`

Owned by each generated app.

Declares:

1. project name
2. target board/soc
3. toolchain/channel/profile
4. enabled modules + revisions
5. features
6. west manifest location
7. app-local module registry overrides (`module_registry`)

Purpose:

- app-local source of truth for enabled module graph
- per-app extension without editing packaged lock data

## Resolution Order

1. Load lock registry.
2. Merge app-local `module_registry` overrides.
3. Resolve requested module + required dependency closure.
4. Validate policy/compatibility against the app target.
5. Materialize source content from curated module locations.
6. Copy or replace vendored `modules/` and `boards/` content inside the app.
7. Update `nsx.yml` and generated `cmake/nsx/modules.cmake`.

`west` remains a source-management mechanism, not the build authority for the
generated app.
