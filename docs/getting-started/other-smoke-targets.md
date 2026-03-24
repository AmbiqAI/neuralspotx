# Other Smoke Targets

In addition to the Apollo510 hardware smoke path, NSX keeps buildable smoke apps
for Apollo4P and Apollo3P-class targets.

These are useful for:

- validating generated-app structure
- checking module and board resolution
- verifying that supported boards still configure and build

## Apollo4P Smoke Build

```bash
cd <nsx-repo>
uv run nsx configure --app-dir ../nsx-apps/smoke_apollo4p_evb
uv run nsx build --app-dir ../nsx-apps/smoke_apollo4p_evb
```

## Apollo3P Smoke Build

```bash
cd <nsx-repo>
uv run nsx configure --app-dir ../nsx-apps/smoke_apollo3p_evb
uv run nsx build --app-dir ../nsx-apps/smoke_apollo3p_evb
```

## When to Use These

Use these smoke targets when:

- changing board metadata
- changing module compatibility
- changing SDK provider selection
- changing shared CMake bootstrap logic
