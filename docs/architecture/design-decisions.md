# Design Decisions

This document captures current NSX design choices that should remain stable
unless explicitly revisited.

## 1. Product Boundary

NSX is primarily a Python tooling product with a thin build-helper payload.

The NSX Python repo owns:

1. the `nsx` CLI and Python API
2. packaged templates
3. packaged CMake helpers
4. metadata schemas and the curated lock registry

The NSX Python repo should not be the long-term source-of-truth location for:

1. firmware module repos
2. board repos
3. full application repos

Current implementation still keeps some firmware content inside the repo during
migration, but that is transitional.

## 2. Workspace Shape

The intended workspace model is:

1. `neuralspot/`: legacy neuralSPOT repo
2. `neuralspotx/` (or future `nsx/`): Python tooling repo
3. `nsx-modules/`: independent module repos
4. `nsx-apps/`: generated or hand-owned app repos

Archive areas may exist temporarily during migration but are not part of the
desired steady-state architecture.

## 3. App Model

NSX apps are lightweight, bare-metal, single-target applications.

An app is expected to target:

1. one board
2. one SoC
3. one toolchain

This is intentional. NSX is not trying to recreate Zephyr device-tree style
multi-board abstraction. Richer board-portable demo applications belong in the
Zephyr side of the ecosystem.

## 4. App Creation Flow

`nsx` is the top-level user interface.

The lifecycle is:

1. `nsx create-app`: create app skeleton, metadata, top-level CMake, and copy
   packaged `cmake/nsx` support
2. dependency resolution: determine the required board/module closure for the
   selected target
3. source materialization: obtain module sources from curated locations
4. vendoring: copy required module and board sources into the app
5. `nsx configure/build/flash/view`: run the CMake-driven app lifecycle

Generated apps should remain understandable as ordinary CMake projects.

## 5. Role of West

`west` is a dependency/source management tool, not the build authority for NSX
apps.

Intended role of `west`:

1. fetch/update module source repos or snapshots
2. provide deterministic source material for vendoring

Intended role of `nsx`:

1. orchestrate app creation
2. resolve module closure
3. copy/replace vendored modules inside apps
4. invoke build/flash/view commands

Intended role of CMake:

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

`cmake/nsx/` is copied from the Python package.
`modules/` and `boards/` are vendored source payloads.

## 7. Board and SoC Policy

Board and SoC are separate decision axes and must remain separate in metadata.

Why:

1. SDK/provider choice is mostly SoC-family driven
2. startup and linker policy are mostly SoC-driven with board-specific tuning
3. some helper/example modules are board-specific because of wiring or EVB
   assumptions

Generated apps store both board and SoC in `nsx.yml`.

## 8. Compatibility Enforcement

Module compatibility must be validated before a module is added to an app.

Each module declares compatibility for:

1. boards
2. socs
3. toolchains

Expected module patterns:

1. generic modules: broad compatibility, usually `*`
2. SoC-family modules: constrained by SoC
3. board-specific modules: constrained by exact board(s)

`nsx module add` should fail fast when the module is incompatible with the
app's current target.

## 9. AmbiqSuite Provider Policy

AmbiqSuite provider modules are versioned by major SDK family and are treated
as target-specific infrastructure modules.

Examples:

1. `nsx-ambiqsuite-r3`
2. `nsx-ambiqsuite-r5`

These are primarily SoC-family constrained, with some board implications
through BSP usage.

For evolving families like R5, NSX should prefer board-specific revision
selection over merging multiple vendor drops into one synthetic SDK snapshot.

That means:

1. one provider repo identity may exist for a family such as `nsx-ambiqsuite-r5`
2. different boards may default to different revisions or branches of that repo
3. the chosen revision must be recorded in generated app metadata
4. temporary locally merged SDK trees are migration scaffolding, not the target
   architecture

## 10. Scope of NSX

NSX is intended for:

1. profiling-oriented apps
2. simple bring-up apps
3. simple interface examples such as WebUSB-style demos
4. lightweight bare-metal workflows

NSX is not intended to become a full-featured demo-application framework.
Those richer application flows belong on the Zephyr side.
