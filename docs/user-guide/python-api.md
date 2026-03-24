# Python API

NSX can be used as a Python library in addition to the `nsx` CLI.

This is useful when building higher-level tools on top of NSX, such as:

- profiling tools
- app generators
- workflow automation
- custom validation utilities

## Import Surface

The `neuralspotx` package exports a small API that mirrors the CLI workflow:

- `init_workspace(...)`
- `create_app(...)`
- `sync_workspace(...)`
- `doctor()`
- `configure_app(...)`
- `build_app(...)`
- `flash_app(...)`
- `view_app(...)`
- `clean_app(...)`
- `add_module(...)`
- `remove_module(...)`
- `update_modules(...)`
- `register_module(...)`

Failures raise `neuralspotx.NSXError`.

## Example

```python
from neuralspotx import NSXError, build_app, configure_app, create_app, init_workspace

workspace = "demo-workspace"
app_dir = f"{workspace}/apps/hello_ap510"

try:
    init_workspace(workspace, skip_update=True)
    create_app(workspace, "hello_ap510", board="apollo510_evb", no_bootstrap=True)
    configure_app(app_dir)
    build_app(app_dir)
except NSXError as exc:
    print(f"NSX failed: {exc}")
```

## Notes

- the current Python API is a thin wrapper over the same implementation used by
  the CLI
- it is intended to mirror CLI behavior closely
- over time, more of the internal workflow can move into library-first
  implementation units
