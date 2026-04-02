# Create an App

This page focuses on `nsx create-app` as the normal entry point for new work.

## Task

Generate a new single-target app for a specific board.

## Command

```bash
nsx create-app <app-dir> --board <board>
```

Example:

```bash
nsx create-app hello_ap510 --board apollo510_evb
```

## What Happens

NSX:

1. creates the app directory
2. writes `nsx.yml`
3. writes the top-level `CMakeLists.txt`
4. copies packaged `cmake/nsx/` support
5. resolves the initial module closure for the selected target
6. vendors modules and board files into the app

## Result

You get a standalone app at:

```text
<app-dir>
```

If you are working from a source checkout, activate the `uv` environment first
and then run the same `nsx ...` command.

See **App Layout** for the resulting structure.
