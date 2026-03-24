# Modules

NSX manages modules as app-local vendored dependencies.

Built-in modules come from the packaged NSX registry. Their default source is
the upstream repo and revision recorded there. Custom modules are registered
explicitly per app.

## List Modules

```bash
cd <nsx-repo>
uv run nsx module list --app-dir <app-dir>
```

This shows the built-in module catalog and highlights which ones are enabled
for the app.

## Add a Module

```bash
cd <nsx-repo>
uv run nsx module add nsx-peripherals --app-dir <app-dir>
```

When you add a module, NSX:

1. resolves dependency closure
2. validates compatibility for board, SoC, and toolchain
3. ensures the built-in source repo is available in the workspace when needed
4. copies the selected module into `app/modules/`
5. updates `nsx.yml` and generated module lists

## Remove a Module

```bash
cd <nsx-repo>
uv run nsx module remove nsx-peripherals --app-dir <app-dir>
```

## Update Modules

```bash
cd <nsx-repo>
uv run nsx module update --app-dir <app-dir>
```

Use this after changing registry defaults or when you want to re-vendor module
content from the configured source revision.

## Register a Custom Module

Use `nsx module register` for local-only modules or custom git repos that are
not part of the built-in NSX catalog.

```bash
cd <nsx-repo>
uv run nsx module register my-custom-module \
  --metadata /path/to/my-custom-module/nsx-module.yaml \
  --project my_custom_repo \
  --project-url https://github.com/myorg/my_custom_repo.git \
  --project-revision main \
  --project-path modules/my_custom_repo \
  --app-dir <app-dir>
```

## Common Constraints

- a module must be compatible with the app target
- dependency cycles are rejected
- SDK provider selection must remain coherent for the target
