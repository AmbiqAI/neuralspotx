# Create an App

This page focuses on `nsx create-app` as the normal entry point for new work.

## Task

Generate a new single-target app for a specific board.

## Command

```bash
cd <nsx-repo>
uv run nsx create-app <workspace> <app-name> --board <board>
```

Example:

```bash
cd <nsx-repo>
uv run nsx create-app <workspace> hello_ap510 --board apollo510_evb
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

You get a standalone app under:

```text
<workspace>/apps/<app-name>
```

See **App Layout** for the resulting structure.
