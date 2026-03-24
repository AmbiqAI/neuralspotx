# Overview

## Purpose

NSX provides a modular build/tooling ecosystem for quickly creating firmware demo
projects for a specific Ambiq board/SoC, with reproducible dependency wiring.

Primary goals:

1. Fast bootstrap for board-specific demo apps.
2. Out-of-tree app builds with vendored app-local build support.
3. Tool-friendly project generation for automation workflows (for example future
   AutoDeploy replacement flows).

## Design Principles

1. AmbiqSuite-first: NSX must support bare-metal AmbiqSuite bring-up as the
   baseline.
2. Modular composition: SoC, board, runtime, and optional features are separate
   modules.
3. Deterministic bootstrap: generated app metadata and lock data must allow
   reproducible setups.
4. Build truth in CMake: metadata orchestrates dependencies; CMake targets remain
   authoritative for compilation/linking.
5. Performance-first default path: for new products and profiling-sensitive
   workflows, NSX should prefer AmbiqSuite-backed targets over Zephyr variants.
6. Single-target apps by default: one app should target one board/SoC/toolchain.

## Current Architecture (Implemented)

1. CMake module layering in NSX:
   - SoC HAL integration
   - board packages
   - runtime core
   - optional portable API
2. Python CLI (`nsx`, from `neuralspotx`) for:
   - workspace init/sync
   - app creation
   - module lifecycle commands
3. Metadata model:
   - per-module `nsx-module.yaml`
   - curated lock file `neuralspotx.data/registry.lock.yaml`
   - per-app `nsx.yml`
4. Generated apps receive:
   - app-local `cmake/nsx/`
   - vendored `modules/`
   - vendored `boards/`

## Near-Term Direction

1. Prioritize out-of-tree vendored app flow as the long-term model.
2. Move module and board sources out of the Python repo over time.
3. Remove monorepo root assumptions over time (for eventual split repos).
4. Promote `nsx` CLI packaging model (PyPI + pipx) while keeping project-local
   deterministic environments.
5. Keep BLE/network/RTOS stacks out of baseline profiles; treat them as optional
   add-on modules.
