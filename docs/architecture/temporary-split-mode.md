# Temporary Split Mode (Local Sibling Repos)

## Purpose

This mode allows NSX split-repo development before upstream repos are published.

## Active Locations

- Modules: `/Users/adampage/Ambiq/neuralspot/nsx-modules/*`
- Built-in boards: `/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/boards/*`
- Tooling boundary: `/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/cmake`
- Standalone apps: `/Users/adampage/Ambiq/neuralspot/nsx-apps/*`

Deprecated or transitional locations:
- `/Users/adampage/Ambiq/neuralspot/neuralspotx/examples`
- `/Users/adampage/Ambiq/neuralspot/legacy`

## Registry policy

- Keep packaged `registry.lock.yaml` stable.
- Use app-local overrides only via `nsx.yml -> module_registry`.

## Register A Local Path Module

```bash
cd <workspace>/apps/<app_name>
uv run nsx module register <module-name> \
  --metadata /abs/path/to/<module>/nsx-module.yaml \
  --project <project-name> \
  --project-local-path /abs/path/to/<module> \
  --override --no-sync
```

Notes:
- `--project-local-path` sources are not west-synced.
- Use `--override` when replacing lockfile mapping.

## Revert to lockfile defaults

Remove app-local mappings from `nsx.yml` under `module_registry` and run:

```bash
uv run nsx module update --no-sync
```

Then re-run west sync if needed:

```bash
uv run nsx sync <workspace>
```
