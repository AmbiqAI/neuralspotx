# `nsx module`

Manages app-local NSX modules.

Subcommands:

- `list`
- `add`
- `remove`
- `update`
- `register`

## `nsx module list`

```text
nsx module list [--app-dir APP_DIR]
```

Example:

```bash
cd <nsx-repo>
uv run nsx module list --app-dir <app-dir>
```

Built-in entries come from the packaged NSX registry.

## `nsx module add`

```text
nsx module add [--app-dir APP_DIR] [--dry-run] [--no-sync] module
```

Example:

```bash
cd <nsx-repo>
uv run nsx module add nsx-peripherals --app-dir <app-dir>
```

For built-in modules, NSX uses the registry's default upstream repo and
revision unless the app overrides that source.

## `nsx module remove`

```text
nsx module remove [--app-dir APP_DIR] [--dry-run] [--no-sync] module
```

## `nsx module update`

```text
nsx module update [--app-dir APP_DIR] [--dry-run] [--no-sync] [module]
```

## `nsx module register`

```text
nsx module register --metadata METADATA --project PROJECT
                    [--project-url PROJECT_URL]
                    [--project-revision PROJECT_REVISION]
                    [--project-path PROJECT_PATH]
                    [--project-local-path PROJECT_LOCAL_PATH]
                    [--app-dir APP_DIR] [--override] [--dry-run] [--no-sync]
                    module
```

Use this when you want to register an external module for one app without
editing the packaged registry.

Use this for local filesystem modules and custom git repos that are not part of
the built-in NSX catalog.

## Common Notes

- `--dry-run` shows changes without writing
- `--no-sync` skips `west update` after manifest changes
- compatibility checks are enforced before module mutation
