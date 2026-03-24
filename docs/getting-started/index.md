# Getting Started

This section is the shortest path from a fresh checkout to a working NSX app.

Recommended order:

1. **Install and Setup** for tool prerequisites and the `uv` environment
2. **First App** for the normal create/configure/build loop
3. **Apollo510 Smoke Test** for the full create/build/flash/view workflow on hardware
4. **Other Smoke Targets** for build-only validation on Apollo4P and Apollo3P

## Working Assumptions

The examples in this documentation use:

- `<nsx-repo>` for the `neuralspotx` repo root
- `<workspace>` for a workspace created with `nsx init-workspace`
- `<app-dir>` for a generated app directory

This keeps the docs portable across different machines and workspace layouts.
