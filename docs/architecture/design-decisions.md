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
3. `boards/`: vendored board definitions for the selected target
4. `cmake/nsx/`: copied NSX build helpers
5. `src/`: app-owned source code

## 3. App Model

NSX apps are lightweight, bare-metal, single-target applications.

From the product perspective, the app is the primary user-facing unit.

Each app targets:

1. one board
2. one SoC
3. one toolchain

## 4. App Creation Flow

`nsx` is the top-level user interface.

The lifecycle is:

1. `nsx create-app`: create app skeleton, metadata, top-level CMake, and copy
   packaged `cmake/nsx` support
2. dependency resolution: determine the required board/module closure for the
   selected target
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

Module compatibility is validated before a module is added to an app.

Each module declares compatibility for:

1. boards
2. socs
3. toolchains

`nsx module add` should fail fast when the module is incompatible with the
app target.

## 9. AmbiqSuite Provider Policy

AmbiqSuite provider modules are treated as target-specific infrastructure
modules.

Examples:

1. `nsx-ambiqsuite-r3`
2. `nsx-ambiqsuite-r4`
3. `nsx-ambiqsuite-r5`

For families with multiple validated minor lines, board defaults pin specific
provider branches or revisions in app metadata.

## 10. Scope of NSX

NSX is intended for:

1. profiling-oriented apps
2. bring-up and smoke-test apps
3. simple interface examples
4. lightweight bare-metal workflows
