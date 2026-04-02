# Python API

NSX can be used as a Python library in addition to the `nsx` CLI.

This is useful when building higher-level tools on top of NSX, such as:

- profiling tools
- app generators
- workflow automation
- custom validation utilities

## Import Surface

The `neuralspotx` package exports a small API that mirrors the CLI workflow:

- `create_app(...)`
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

## Module Management From Python

The Python API exposes the same two module flows as the CLI:

- `add_module(...)` for built-in first-class modules from the packaged registry
- `register_module(...)` for app-local custom modules from a local path or a git-backed project definition

## Example: Direct Calls

```python
from neuralspotx import NSXError, build_app, configure_app, create_app

app_dir = "hello_ap510"

try:
    create_app(app_dir, board="apollo510_evb", no_bootstrap=True)
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
    build_app,
    create_app,
)

create_app(
    AppCreateRequest(
        app_dir="hello_ap510",
        board="apollo510_evb",
        no_bootstrap=True,
    )
)
build_app(
    AppBuildRequest(
        app_dir="hello_ap510",
        jobs=4,
    )
)
```

## Example: Add A Built-In Module

```python
from neuralspotx import add_module

add_module("hello_ap510", "nsx-peripherals")
```

## Example: Register A Local Custom Module

```python
from neuralspotx import register_module

register_module(
    app_dir="hello_ap510",
    module="my-custom-module",
    metadata="/path/to/my-custom-module/nsx-module.yaml",
    project="my_custom_repo",
    project_local_path="/path/to/my-custom-module",
)
```

## Example: Register A Git-Backed Custom Module

```python
from neuralspotx import register_module

register_module(
    app_dir="hello_ap510",
    module="my-custom-module",
    metadata="/path/to/my-custom-module/nsx-module.yaml",
    project="my_custom_repo",
    project_url="https://github.com/myorg/my_custom_repo.git",
    project_revision="main",
    project_path="modules/my_custom_repo",
)
```

## Notes

- dataclass request objects give higher-level tools a cleaner typed integration
  surface
- the API is suitable for tools built on top of NSX, such as profilers,
  validators, and app generators
- the API raises `NSXError` for workflow failures instead of exposing argparse
  behavior directly
