# AP510 Smoke Test

This is the canonical bare-metal NSX smoke test for the Apollo510 EVB.

It verifies:
- app generation
- module vendoring
- configure/build
- flash
- SWO output through `nsx view`

## Prerequisites

- Apollo510 EVB connected over USB/J-Link
- Arm GNU toolchain in `PATH`
- SEGGER `JLinkExe` and `JLinkSWOViewerCL` in `PATH`
- NSX repo synced:

```bash
cd /Users/adampage/Ambiq/neuralspot/neuralspotx
uv sync
```

## Existing Reference App

The checked-in reference app is:

- [`/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb`](/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb)

From the NSX repo root:

```bash
cd /Users/adampage/Ambiq/neuralspot/neuralspotx
uv run nsx configure --app-dir /Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb
uv run nsx build --app-dir /Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb
uv run nsx flash --app-dir /Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb
uv run nsx view --app-dir /Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb
```

Expected SWO output:

```text
nsx hello from generated app
nsx hello from generated app
...
```

## Fresh App Generation

Create a fresh workspace and app:

```bash
cd /Users/adampage/Ambiq/neuralspot/neuralspotx
uv run nsx init-workspace /tmp/nsx-ap510-smoke --skip-update
uv run nsx create-app /tmp/nsx-ap510-smoke hello_ap510_smoke --board apollo510_evb
```

Build and run it:

```bash
cd /Users/adampage/Ambiq/neuralspot/neuralspotx
uv run nsx configure --app-dir /tmp/nsx-ap510-smoke/apps/hello_ap510_smoke
uv run nsx build --app-dir /tmp/nsx-ap510-smoke/apps/hello_ap510_smoke
uv run nsx flash --app-dir /tmp/nsx-ap510-smoke/apps/hello_ap510_smoke
uv run nsx view --app-dir /tmp/nsx-ap510-smoke/apps/hello_ap510_smoke
```

## Notes

- Generated apps vendor their modules under `app/modules/` and their board definition under `app/boards/`.
- `cmake/nsx/` is copied from the packaged Python repo assets and is the source of flash/view behavior inside the generated app.
- The smoke-test app intentionally prints once per second so SWO attach timing is forgiving.
