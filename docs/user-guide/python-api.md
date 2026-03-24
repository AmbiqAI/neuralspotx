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

The API supports two styles:

- direct function arguments
- dataclass request objects

The Python API and CLI now share the same non-argparse implementation layer.
That means:

- the CLI remains the main user-facing entry point
- higher-level Python tools can call NSX directly without shelling out
- API tests and CLI behavior exercise the same workflow logic

## Example: Direct Calls

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

## Example: Dataclass Requests

```python
from neuralspotx import (
    AppBuildRequest,
    AppCreateRequest,
    WorkspaceInitRequest,
    build_app,
    create_app,
    init_workspace,
)

init_workspace(WorkspaceInitRequest(workspace="demo-workspace", skip_update=True))
create_app(
    AppCreateRequest(
        workspace="demo-workspace",
        name="hello_ap510",
        board="apollo510_evb",
        no_bootstrap=True,
    )
)
build_app(
    AppBuildRequest(
        app_dir="demo-workspace/apps/hello_ap510",
        jobs=4,
    )
)
```

## Notes

- dataclass request objects give higher-level tools a cleaner typed integration
  surface
- the API is suitable for tools built on top of NSX, such as profilers,
  validators, and app generators
- the API raises `NSXError` for workflow failures instead of exposing argparse
  behavior directly
