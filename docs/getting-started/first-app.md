# First App

This page walks through the standard NSX workspace-first app creation flow.

## Goal

Create a minimal app, configure it, and build it successfully.

## Step 1: Initialize a Workspace

Check the local environment first:

```bash
cd <nsx-repo>
uv run nsx doctor
```

Then initialize a workspace:

```bash
cd <nsx-repo>
uv run nsx init-workspace <workspace>
```

This creates a workspace with:

- `manifest/`
- `neuralspotx/`
- `modules/`
- `apps/`

## Step 2: Create an App

```bash
cd <nsx-repo>
uv run nsx create-app <workspace> hello_ap510 --board apollo510_evb
```

This creates a generated app at:

```text
<workspace>/apps/hello_ap510
```

## Step 3: Configure the App

```bash
cd <nsx-repo>
uv run nsx configure --app-dir <workspace>/apps/hello_ap510
```

## Step 4: Build the App

```bash
cd <nsx-repo>
uv run nsx build --app-dir <workspace>/apps/hello_ap510
```

## What to Expect

The generated app contains:

- `CMakeLists.txt`
- `nsx.yml`
- `src/`
- `cmake/nsx/`
- `modules/`
- `boards/`

At this point you have a standalone app with vendored board and module content.

## Next Steps

- See **App Layout** for a breakdown of the generated structure
- See **Apollo510 Smoke Test** for hardware flashing and SWO output
- See **Modules** if you want to add or remove app dependencies
