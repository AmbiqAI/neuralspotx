# External NSX App Template

This template shows a standalone NSX app with app-local modules and board content.

## Create

```bash
nsx create-app coremark --board apollo510_evb
cd coremark
```

## Build

```bash
nsx configure --app-dir .
nsx build --app-dir .
nsx flash --app-dir .
nsx view --app-dir .
```

`nsx view` opens the SEGGER SWO viewer first and then runs the app's normal
reset target once. This keeps the standard `Reset` behavior while avoiding an
empty SWO session when the target is already running before the viewer attaches.

Expected SWO output after `flash` + `view`:

```text
nsx hello from generated app
nsx hello from generated app
...
```

## Layout

- `cmake/nsx/` contains copied NSX CMake support.
- `modules/` contains NSX module sources managed inside this app.
- `boards/` contains the vendored board definition for the selected target.
- `nsx.yml` tracks the app board and enabled module set.
- Use `--no-reset-on-open` only if you explicitly want to attach without the automatic reset.

If you are using a source checkout instead of a `pipx` install, activate the
`uv` environment first and then run the same `nsx ...` commands.
