# Build, Flash, and View

NSX wraps the normal firmware lifecycle around generated CMake targets.

## Configure

```bash
cd <nsx-repo>
uv run nsx configure --app-dir <app-dir>
```

## Build

```bash
cd <nsx-repo>
uv run nsx build --app-dir <app-dir>
```

## Flash

```bash
cd <nsx-repo>
uv run nsx flash --app-dir <app-dir>
```

This builds the app if needed and then invokes the SEGGER flash path defined by
the app’s generated CMake support.

## View SWO Output

```bash
cd <nsx-repo>
uv run nsx view --app-dir <app-dir>
```

`nsx view` launches the SEGGER SWO viewer for the active board target.

## Clean

```bash
cd <nsx-repo>
uv run nsx clean --app-dir <app-dir>
```

## Typical Sequence

```bash
cd <nsx-repo>
uv run nsx configure --app-dir <app-dir>
uv run nsx build --app-dir <app-dir>
uv run nsx flash --app-dir <app-dir>
uv run nsx view --app-dir <app-dir>
```
