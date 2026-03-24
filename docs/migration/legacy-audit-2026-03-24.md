# Legacy Audit (2026-03-24)

This audit captures the main leftover folders and code paths after the AP510
vendored-app flow was validated end to end.

## Validated Current Path

The current working path is:

- Python tooling repo:
  - [`/Users/adampage/Ambiq/neuralspot/neuralspotx`](/Users/adampage/Ambiq/neuralspot/neuralspotx)
- Module repos:
  - [`/Users/adampage/Ambiq/neuralspot/nsx-modules`](/Users/adampage/Ambiq/neuralspot/nsx-modules)
- Built-in board definitions:
  - [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/boards`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/boards)
- Standalone apps:
  - [`/Users/adampage/Ambiq/neuralspot/nsx-apps`](/Users/adampage/Ambiq/neuralspot/nsx-apps)

Verified AP510 apps:

- [`/Users/adampage/Ambiq/neuralspot/nsx-apps/hello_ap510_latest`](/Users/adampage/Ambiq/neuralspot/nsx-apps/hello_ap510_latest)
- fresh generated app:
  - `/private/tmp/nsx-ap510-smoke.ORL3Sw/apps/hello_ap510_smoke`

## Legacy Or Transitional Areas

### 0. External board root

The former external board root was moved to:

- [`/Users/adampage/Ambiq/neuralspot/legacy/archived-workspace/nsx-boards-legacy`](/Users/adampage/Ambiq/neuralspot/legacy/archived-workspace/nsx-boards-legacy)

Status:

- board definitions are now packaged with the Python tooling under `src/neuralspotx/boards`
- generated apps vendor boards from the packaged tooling path

### 1. Repo-local in-tree examples

These are still present under:

- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/examples`](/Users/adampage/Ambiq/neuralspot/neuralspotx/examples)

Original contents at the time of the audit:

- `hello_ap3p`
- `hello_ap3p_with_nsx`
- `hello_ap510_evb`
- `hello_ap510_vendored`

Status:

- `hello_ap510_vendored` was archived to [`/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/hello_ap510_vendored`](/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/hello_ap510_vendored)
- the remaining non-vendored in-tree examples are still tied to the repo-top CMake build model rather than the preferred `nsx create-app` standalone flow.

Recommendation:

- either regenerate these from `nsx create-app` and keep them as current fixtures, or archive/remove them.

### 2. Empty repo-local split roots

These folders existed in the Python repo during the transition but no longer
carry active source:

- `neuralspotx/modules`
- `neuralspotx/boards`
- `neuralspotx/cmake`

Status:

- `modules/` and `boards/` have been removed from the active repo root.
- the old top-level `cmake/` stub was archived to [`/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/cmake-legacy`](/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/cmake-legacy)
- active packaged CMake assets live under [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/cmake`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/cmake)

Recommendation:

- remove these empty directories once no tooling or docs refer to them.

### 3. Vendor leftovers

Archived location:

- [`/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/vendor-legacy`](/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/vendor-legacy)

Contents include:

- `vendor/ns`
- `vendor/nsx_portable`
- `vendor/nsx_board_helpers_apollo3p`

Status:

- these appear to be migration leftovers
- active AP510 flow no longer depends on them
- they still overlap conceptually with migrated modules like `nsx-portable-api`

Recommendation:

- confirm no active references remain outside archived or stale example content, then archive/remove this folder.

### 4. Stale package metadata

Archived location:

- [`/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/generated-metadata`](/Users/adampage/Ambiq/neuralspot/legacy/neuralspotx/archived-repo/generated-metadata)

Status:

- `neuralspotx_tools.egg-info` still references `nsx_cli`
- top-level `neuralspotx.egg-info` still reflects the pre-`src` package layout
- these are no longer in the active repo root

Recommendation:

- regenerate or remove stale egg-info content so future searches do not surface obsolete package paths.

### 5. Stale docs

Known stale doc:

- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/architecture/temporary-split-mode.md`](/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/architecture/temporary-split-mode.md)

Status:

- this has been updated to the current sibling-root split model in the same cleanup pass as this audit

### 6. Legacy top-level workspace areas

Still present outside the Python repo:

- [`/Users/adampage/Ambiq/neuralspot/legacy/starters`](/Users/adampage/Ambiq/neuralspot/legacy/starters)
- [`/Users/adampage/Ambiq/neuralspot/legacy/archived-workspace/nsx-apps-legacy`](/Users/adampage/Ambiq/neuralspot/legacy/archived-workspace/nsx-apps-legacy)

Status:

- these remain as migration reference or legacy starter material
- they are not part of the validated NSX app flow

Recommendation:

- keep archived for now, but do not treat them as active references

### 7. Unmigrated non-NSX module repos

Still present in the module root:

- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-features`](/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-features)
- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-sensors`](/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-sensors)
- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-physiokit`](/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-physiokit)
- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-tileio`](/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-tileio)
- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-as7058`](/Users/adampage/Ambiq/neuralspot/nsx-modules/ns-as7058)
- [`/Users/adampage/Ambiq/neuralspot/nsx-modules/cmsis-nn`](/Users/adampage/Ambiq/neuralspot/nsx-modules/cmsis-nn)

Status:

- these are not yet normalized into `nsx-*` module naming and metadata flow

Recommendation:

- decide module by module whether each becomes:
  - a first-class `nsx-*` module
  - a third-party imported dependency
  - or archived legacy inventory
