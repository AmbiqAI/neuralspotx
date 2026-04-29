# `nsx module`

Manages app-local NSX modules.

Subcommands:

- `list`
- `describe`
- `search`
- `add`
- `remove`
- `update`
- `init`
- `register`
- `validate`

## `nsx module list`

```text
nsx module list [--app-dir APP_DIR] [--registry-only] [--json]
```

Example:

```bash
nsx module list --app-dir <app-dir>
```

Built-in entries come from the packaged NSX registry.

Machine-readable example:

```bash
nsx module list --registry-only --json
```

## `nsx module describe`

```text
nsx module describe [--app-dir APP_DIR] [--json] module
```

Examples:

```bash
nsx module describe nsx-pmu-armv8m --app-dir <app-dir>
nsx module describe nsx-pmu-armv8m --json
```

`describe` is intended as the per-module discovery surface for tools and agents.
When metadata can be resolved, it includes dependency, compatibility, target,
and optional capability information from `nsx-module.yaml`.
Use `--app-dir` for app-local effective registry resolution.

## `nsx module search`

```text
nsx module search [--app-dir APP_DIR]
                  [--board BOARD] [--soc SOC] [--toolchain TOOLCHAIN]
                  [--include-incompatible] [--json]
                  query
```

Examples:

```bash
nsx module search profiling --app-dir <app-dir>
nsx module search pmu --soc apollo510 --json
```

`search` is intended as the query surface for tools and agents.
It searches current module metadata such as:

- module names
- module type and optional category/provider fields
- exported CMake targets
- required and optional dependencies
- compatibility fields
- `provides.features`
- optional future semantic fields such as `capabilities`, `use_cases`, or `summary`

When `--app-dir` is provided, NSX uses the app-effective registry and the app's
target context by default. Use `--include-incompatible` if you want to keep
non-matching results in the output for comparison or planning.

## `nsx module add`

```text
nsx module add [--app-dir APP_DIR] [--local] [--vendored] [--dry-run] module
```

Example:

```bash
nsx module add nsx-peripherals --app-dir <app-dir>
```

For built-in modules, NSX uses the registry's default upstream repo and
revision unless the app overrides that source.

This is the standard way to install a supported first-class module into an app.

### `--vendored`

Scaffold a custom module that lives **inside this app's git repository**
and is never touched by `nsx sync`. Useful for AOT-generated modules,
in-house drivers, or any code that needs to be source-controlled with
the app itself.

```bash
nsx module add my-aot-stub --vendored
```

This creates `modules/my-aot-stub/` with a minimal `nsx-module.yaml` and
`CMakeLists.txt`, appends

```yaml
- name: my-aot-stub
  source: { vendored: true }
```

to `nsx.yml`, regenerates `modules/.gitignore` so the directory is **not**
ignored, and refreshes `nsx.lock` so the module's content hash is
recorded. Edit the scaffolded `CMakeLists.txt` to add your sources, then
re-run `nsx lock`.

### `--local`

Mark the module as a local mirror — the on-disk copy under
`modules/<name>/` is regenerated from an external source path on every
sync. The path is configured by either the
[`source: { path: <p> }`](#source-field) shorthand on the module entry
or by setting `module_registry.modules.<name>.local_path` directly.

## `nsx module remove`

```text
nsx module remove [--app-dir APP_DIR] [--dry-run] module
```

## `nsx module update`

```text
nsx module update [--app-dir APP_DIR] [--dry-run] [module]
```

## `nsx module init`

```text
nsx module init [--name NAME] [--type TYPE] [--summary SUMMARY]
                                [--version VERSION]
                                [--dependency DEPENDENCY]
                                [--board BOARD] [--soc SOC] [--toolchain TOOLCHAIN]
                                [--force]
                                module_dir
```

Examples:

```bash
nsx module init my-sensor-driver

nsx module init my-sensor-driver \
    --type backend_specific \
    --summary "I2C driver for the XYZ ambient light sensor." \
    --dependency nsx-core \
    --dependency nsx-i2c \
    --soc apollo510 \
    --soc apollo510b \
    --soc apollo5b
```

Creates a standard custom-module skeleton with:

- `nsx-module.yaml`
- `CMakeLists.txt`
- `README.md`
- `includes-api/<module_name>/...`
- `src/<module_name>.c`

Use this as the normal starting point for third-party and app-local modules,
then validate and register the generated module.

## `nsx module register`

```text
nsx module register --metadata METADATA --project PROJECT
                    [--project-url PROJECT_URL]
                    [--project-revision PROJECT_REVISION]
                    [--project-path PROJECT_PATH]
                    [--project-local-path PROJECT_LOCAL_PATH]
                    [--app-dir APP_DIR] [--override] [--dry-run]
                    module
```

Use this when you want to register an external module for one app without
editing the packaged registry.

Use this for local filesystem modules and custom git repos that are not part of
the built-in NSX catalog.

## `nsx module validate`

```text
nsx module validate [--json] metadata
```

Examples:

```bash
nsx module validate path/to/nsx-module.yaml
nsx module validate path/to/nsx-module.yaml --json
```

Validates that an `nsx-module.yaml` file has all required fields and valid
values. Use this before registering a custom module to catch errors early.

Checks include:

- `schema_version` is `1`
- `module.name`, `module.type`, `module.version` are present and valid
- `module.type` is one of the supported types
- `support.ambiqsuite` is `true`
- `build.cmake.package` and `build.cmake.targets` are present and non-empty
- `depends.required` and `depends.optional` are present
- `compatibility.boards`, `compatibility.socs`, `compatibility.toolchains` are non-empty

Local filesystem example:

```bash
nsx module register my-custom-module \
    --metadata /path/to/my-custom-module/nsx-module.yaml \
    --project my_custom_repo \
    --project-local-path /path/to/my-custom-module \
    --app-dir <app-dir>
```

Git-backed example:

```bash
nsx module register my-custom-module \
    --metadata /path/to/my-custom-module/nsx-module.yaml \
    --project my_custom_repo \
    --project-url https://github.com/myorg/my_custom_repo.git \
    --project-revision main \
    --project-path modules/my_custom_repo \
    --app-dir <app-dir>
```

`register` writes an app-local override into `nsx.yml` and then vendors the
registered module into that app.

## Common Notes

- `--dry-run` shows changes without writing
- compatibility checks are enforced before module mutation
