# NSX Architecture Docs

This directory captures the evolving NSX architecture as implementation lands.

Current docs:

- `overview.md`: system boundaries, goals, and current state.
- `design-decisions.md`: explicit architecture decisions and current intended operating model.
- `module-model.md`: module classes, package contracts, and backend rules.
- `metadata-model.md`: `nsx-module.yaml`, `registry.lock.yaml`, and `nsx.yml` roles.
- `sdk-provider-model.md`: versioned AmbiqSuite provider model and board/provider binding.
- `sdk-upstream-plan.md`: recommended upstream branch structure for raw SDK provider repos.
- `board-coverage.md`: built-in board coverage and current gaps relative to legacy neuralSPOT.
- `migration-from-monorepo.md`: migration steps away from root `neuralSPOT` path coupling.
- `roadmap.md`: staged migration from monorepo-local to split repos + PyPI tooling.
- `temporary-split-mode.md`: local sibling-repo workflow with app-local module overrides.
- `upstream-migration-checklist.md`: checklist for moving from local nested repos to remote repos.

Related docs outside this folder:

- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/getting-started/ap510-smoke-test.md`](/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/getting-started/ap510-smoke-test.md): validated AP510 smoke-test flow.
- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/migration/legacy-audit-2026-03-24.md`](/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/migration/legacy-audit-2026-03-24.md): current legacy/transitional inventory.

Scope notes:

- NSX is AmbiqSuite-first.
- NSX modules may support AmbiqSuite-only or AmbiqSuite+Zephyr.
- Zephyr-only modules are out of NSX registry scope.
