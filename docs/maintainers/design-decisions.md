# Design Decisions

This document captures the design choices that define the current NSX workflow.

## 1. Product Boundary

NSX is primarily a Python tooling product with a thin build-helper payload.

The Python repo owns:

1. the `nsx` CLI and Python API
2. packaged templates
3. packaged CMake helpers
4. metadata schemas and the curated lock registry
5. built-in board definitions

Firmware modules remain separate repos.

## 2. App Shape

The intended working layout after `nsx create-app` is:

1. `nsx.yml`: app metadata and module state
2. `modules/`: vendored module content resolved from the packaged registry
3. `boards/`: vendored board definitions required by the app's target set
4. `cmake/nsx/`: copied NSX build helpers
5. `src/`: app-owned source code

## 3. App Model

NSX apps are lightweight bare-metal applications with an explicit supported
target set and one active target per operation.

From the product perspective, the app is the primary user-facing unit.

Each declared target resolves:

1. one board
2. its SoC and starter profile
3. its effective toolchain

`targets.default` supplies the active board unless a lifecycle command selects
another member of `targets.supported` with `--board`. Legacy singular
`target:` manifests remain a compatibility input, not the preferred shape for
new multi-target manifests.

## 4. App Creation Flow

`nsx` is the top-level user interface.

The lifecycle is:

1. `nsx create-app`: create app skeleton, metadata, top-level CMake, and copy
   packaged `cmake/nsx` support
2. dependency resolution: determine the required board/module closure for the
   initial selected target (and each declared target when the set is expanded)
3. source materialization: obtain module sources from curated registry-backed locations
4. vendoring: copy required module and board sources into the app
5. `nsx configure/build/flash/view`: run the CMake-driven app lifecycle

Generated apps remain understandable as ordinary CMake projects.

## 5. Module Source Resolution

Module sources are resolved from the packaged registry and cloned from their
upstream git repos on demand.

Role of git:

1. clone or fetch module source repos
2. provide deterministic source material for vendoring

Role of `nsx`:

1. orchestrate app creation
2. resolve module closure
3. copy or replace vendored modules inside apps
4. invoke build, flash, and view commands

Role of CMake:

1. remain the build truth for compilation and linking
2. express startup, linker, SDK, and target wiring

## 6. Vendored App Contents

Generated apps should be mostly self-contained after creation.

Expected layout:

1. `CMakeLists.txt`
2. `nsx.yml`
3. `src/`
4. `cmake/nsx/`
5. `modules/`
6. `boards/`

## 7. Board and SoC Policy

Board and SoC remain separate decision axes.

Why:

1. SDK/provider choice is mostly SoC-family driven
2. startup and linker policy are mostly SoC-driven with board-specific tuning
3. some helper modules are board-specific because of wiring or EVB assumptions

## 8. Compatibility Enforcement

Module compatibility is validated against the targets to which a dependency
applies before it is added to an app.

Each module declares compatibility for:

1. boards
2. socs
3. toolchains

`nsx module add` fails fast when the module is incompatible with an applicable
supported target. A board-scoped dependency must name a subset of
`targets.supported`.

## 9. AmbiqSuite Provider Policy

AmbiqSuite provider modules are treated as target-specific infrastructure
modules.

A single provider module, `nsx-ambiqsuite`, mirrors the upstream AmbiqSuite
`stable` baseline and serves every supported Apollo SoC.

For families with multiple validated minor lines, board defaults pin specific
provider revisions in app metadata.

The Corstone family resolves the firmware provider `nsx-corstone-sdk` and
selects its BSP using contract 2. Module manifests opt in with `support.corstone`.
The board selects the execution platform independently of application sources.
The application vendors firmware inputs. Arm distributes the host simulator separately.

## 10. Scope of NSX

NSX is intended for:

1. profiling-oriented apps
2. bring-up and smoke-test apps
3. simple interface examples
4. lightweight bare-metal workflows

## Build-local module inputs

The selected board's module closure is emitted to
`<build-dir>/nsx/modules.cmake`. The source-tree `cmake/nsx/modules.cmake`
entry point is a stable loader for that file, so existing app CMakeLists do not
need string rewrites. Lock/sync seed the default board build directory;
configure and incremental build operations refresh the selected build directory
from its lock, including custom paths. Different boards no longer overwrite
one another's CMake module list. Shared app-local vendoring and its coordination
remain unchanged; concurrent dependency updates are not isolated source trees.

## Targeted lock updates

A nonempty update selection expands module names to Git registry projects within
each target closure, matching the unit of app-local vendoring. Unrelated matching
project/URL/constraint resolutions may be reused even for floating refs. The shared
lock path prepares target closures once and validates selected names before writes;
its prefetch and final resolution passes use the same reuse policy. Current metadata determines the closure. Plain lock preserves matching branch
commits. Authored Git fields follow registry layer precedence. An incompatible
packaged default for an unselected project requires an explicit update. All board
sections publish in one atomic lock write after preparation succeeds. Targeted results reject incompatible artifacts
sharing a source directory before writing that target section. The locking guide
documents CLI/API selection, cache, check and metadata limits.

## Advisory console metadata exception

Optional `console` declarations (app defaults and per-board overrides) extend
manifest schema 2 without changing existing build or dependency semantics. Older
readers preserve but ignore these declarations, losing only transport warnings.
This narrow exception does not permit unversioned changes to dependency resolution,
build semantics, locks, or other schemas. Exact schema checks and the no-migration
policy remain in force.

## Custom board composition

A board descriptor selects one BSP provider and contract version. The SDK defines
and qualifies the interface; NSX binds required role edges, orders the provider
before consumers, vendors sources locally, and records the composition per target
in lock schema 5. Contract 1 is reserved for the built-in adapter. Contract 2
requires explicit provider metadata and target-owned SDK validation.

Inherited descriptors are app-local snapshots. A custom board includes SDK silicon
support and its own optional flags/memory/debug fragments; it never includes its
parent EVB's aggregate CMake. SDK adoption of a board can change the BSP binding
without changing board identity. See the published Add a board guide for authoring.

## Standalone CMake inputs

Prepared apps have board-scoped generated inputs under `cmake/nsx-resolved/`,
outside the pinned packaged tooling tree. Creation publishes after final manifest
save and dependency acquisition; sync publishes after materialized verification.
Ordinary build refreshes must never rebaseline declaration fingerprints. Changed
locks invalidate their board's snapshot until preparation succeeds. Direct CMake
consumes that snapshot, checks declarations and registers regeneration dependencies;
it never calls Python or performs NSX dependency resolution. This is declaration
drift detection, not full frozen-source verification. Keep legacy build-local
inputs for old loaders and preserve pinned loaders during frozen sync. Sharing
requires ignored vendored/generated content as well as authored files.

Compiler compatibility is advisory in CMake, preserving the existing explicit
CLI toolchain override behavior. Resolution continues to enforce the manifest's
toolchain. Do not turn standalone support into a new qualification gate: pinned
SDK metadata can intentionally describe fewer toolchains than existing example
build coverage (FreeRTOS in SDK 5.2.30 declares GCC while CI builds ATFE).

## Configured debug context and probe policy

The internal schema-1 debug handoff is opt-in (`NSX_DEBUG_CONTEXT=ON` and
`NSX_DEBUG_INPUT_CONTRACT=1`). App flash/view/reset/RTT require it; legacy
build-only and direct CMake paths remain supported. CMake owns evaluated settings, producer paths, recipes, preparation and
capture; the typed internal Python reader validates and manages private-copy
lifetime. There is no public backend ABI or alternate Python recipe renderer.

The new protocol requires CMake 3.31+ with cmakeFiles 1.1 and single-configuration
Ninja. Build-only and direct CMake retain their existing minimum requirements. Source authors
must register external textual setting reads with `nsx_debug_read_text`; opt-in
is an obligation, not proof that arbitrary CMake/environment dependencies are
tracked. Flat glob membership preserves directory inclusion and entry types;
recursive/relative/symlink-following globs are unsupported.

Preparation is an explicit script, never a nested Ninja configure target. It
invalidates the old document, bootstraps configure, compares two further
snapshots, and atomically publishes one build-level document. The reader checks
exact schema/identity, recorded input content, glob membership, and agreement
with the evaluated raw generation. Attach inspection never configures/builds.
Input/output writers must remain quiescent during preparation and capture;
hash comparisons are not a filesystem transaction or an ABA guarantee.

Capture copies operation inputs into a caller-owned temporary directory outside
the source/build trees, validates around the copy, and renders flash commands
using the producer's template. Keep the snapshot alive until every related
process stops. Flash callers must build first; RTT callers must analyze the
copied ELF. Neither protocol proves running firmware identity. Explicit serials are temporary overrides; omission inherits the evaluated target
preference or discovers one eligible USB probe; explicit discovery ignores the
preference. Resolve once with no fallback. Explicit configure sets/clears the cache
preference; implicit reconfiguration preserves a validated owned preference.
Malformed/wrong-identity contexts fail before writes or hardware; only typed
freshness failures may trigger permitted preparation. Frozen verification precedes
all potentially regenerating build steps. No automatic helper upgrade or contract
certification is allowed. Initial template opt-in is bounded to default/blinky on
Apollo510 EVB/GCC; other graphs require explicit authored adoption/qualification.
