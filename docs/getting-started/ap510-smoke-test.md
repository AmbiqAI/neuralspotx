# Apollo510 Smoke Test

This is the canonical NSX hardware smoke test for the Apollo510 EVB.

It verifies:

- app generation
- module vendoring
- configure and build
- flash
- SWO output through `nsx view`

## Prerequisites

- Apollo510 EVB connected over USB or J-Link
- Arm GNU toolchain in `PATH`
- SEGGER `JLinkExe` and `JLinkSWOViewerCL` in `PATH`
- NSX environment already synced

```bash
cd <nsx-repo>
uv sync
```

## Reference Smoke App

The checked-in reference app is:

```text
../nsx-apps/smoke_apollo510_evb
```

Run the full loop:

```bash
cd <nsx-repo>
uv run nsx configure --app-dir ../nsx-apps/smoke_apollo510_evb
uv run nsx build --app-dir ../nsx-apps/smoke_apollo510_evb
uv run nsx flash --app-dir ../nsx-apps/smoke_apollo510_evb
uv run nsx view --app-dir ../nsx-apps/smoke_apollo510_evb
```

Expected SWO output:

```text
nsx hello from generated app
nsx hello from generated app
...
```

## Fresh App Flow

Create a fresh workspace and app:

```bash
cd <nsx-repo>
uv run nsx init-workspace <workspace> --skip-update
uv run nsx create-app <workspace> hello_ap510_smoke --board apollo510_evb
```

Build, flash, and view it:

```bash
cd <nsx-repo>
uv run nsx configure --app-dir <workspace>/apps/hello_ap510_smoke
uv run nsx build --app-dir <workspace>/apps/hello_ap510_smoke
uv run nsx flash --app-dir <workspace>/apps/hello_ap510_smoke
uv run nsx view --app-dir <workspace>/apps/hello_ap510_smoke
```

## Notes

- generated apps vendor modules under `app/modules/`
- generated apps vendor board definitions under `app/boards/`
- `cmake/nsx/` is copied from the packaged tooling assets
- the smoke app prints once per second so SWO attach timing is forgiving
