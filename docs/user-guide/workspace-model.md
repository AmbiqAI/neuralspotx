# Workspace Model

NSX separates the tooling repo, fetched module repos, and generated apps.

## Typical Layout

After `nsx init-workspace`, a workspace looks like this:

```text
<workspace>/
  manifest/
  neuralspotx/
  modules/
  apps/
```

## Roles

- `manifest/` holds the west manifest
- `neuralspotx/` is the tooling repo used to run `nsx`
- `modules/` holds built-in and custom module repos materialized by `west`
- `apps/` holds generated or hand-owned applications

## Important Rule

The generated app is the unit you build, flash, and debug.

NSX uses workspace-level source repos to materialize built-in modules, but the
app itself vendors the board and module content it needs for configure, build,
flash, and view.
