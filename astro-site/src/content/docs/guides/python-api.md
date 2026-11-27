---
title: Python API guide
description: Drive NSX from Python instead of the shell, handle its results and errors, and give an agent a machine-readable view of the CLI.
---

The CLI and Python API share workflow operations. Use it when you want a build matrix, a bring-up script, a test harness,
or NSX wired into a larger tool.

Every public symbol and signature is in the generated
[Python API reference](/neuralspotx/reference/api/). This page is how to start and what to
watch for.

:::note[Python API compatibility]
The 0.x exports are provisional. Starting at 1.0, the documented exports and calling
conventions follow the [1.x compatibility policy](/neuralspotx/reference/releases/#compatibility-policy-for-1x).
:::

## The shape of it

```python
from pathlib import Path
from neuralspotx import build_app, configure_app, create_app

app_dir = create_app(Path("hello_ap510"), board="apollo510_evb")
configure_app(app_dir)
build_app(app_dir)
```

Most app lifecycle functions take the app directory or a request object as their first
argument, with additional function options passed by keyword. Request dataclasses also
accept positional fields; prefer keywords when constructing them.

There are deliberate exceptions. `reset_target` takes keyword arguments only;
`resolve_rtt_app` and `rtt_app` require an `AppRttRequest`. Module functions such as
`add_module` also accept a positional module name, and registry and inspection helpers
have their own signatures. Consult the generated reference for each function.
Operations report failures through exceptions rather than error-code return values.

The supported Python imports are the names in `neuralspotx.__all__` and
`neuralspotx.api.__all__`. `PathLike` is available from `neuralspotx.api`.
Implementation packages such as `neuralspotx.operations` and private modules are not
extension APIs. The existing `neuralspotx.api.operations` attribute remains importable
for compatibility, but is not a supported export.

`describe_board(name, app_dir=app_dir)` returns the board descriptor used by that
app, including facts inherited from its parent board. Omit `app_dir` to inspect
the packaged board regardless of the Python process's working directory.

## Two calling styles

Keyword arguments are the direct style:

```python
build_app(app_dir, board="apollo4p_blue_kxr_evb", toolchain="armclang", jobs=16)
```

Request dataclasses are the other, and they are better when you are building a call
programmatically or passing one around:

```python
from neuralspotx import AppBuildRequest, build_app

request = AppBuildRequest(app_dir=app_dir, board="apollo510_evb", frozen=True)
build_app(request)
```

When passing a request, set operation options on the request. You may repeat an
option with an equal value (use the same string or `Path` representation for paths). A conflicting argument raises `NSXConfigError` before the
operation starts, even when you explicitly pass a default such as `False`, `8`
or `None`. Omitted arguments keep the request's values. Callbacks such as `emit`
and `on_line` belong to the call and can accompany either style.

To change one field for a single call, copy the request:

```python
from dataclasses import replace
from neuralspotx import AppLockRequest, lock_app

build_app(replace(request, jobs=4), on_line=print)
lock_app(AppLockRequest(app_dir, check=True))  # check without writing nsx.lock
```

In 1.x, reusing a request for another operation can produce a `DeprecationWarning`.
For example, configure accepts an `AppBuildRequest` but ignores its build-only
`jobs` option. If an operation cannot honor `frozen=True`, it raises
`NSXConfigError` before starting. `init_module(ModuleInitRequest(...), ...)` retains its documented
request precedence and emits a `DeprecationWarning` for conflicting arguments.
Use `replace()` there as well.

The exported request types include: `AppActionRequest`,
`AppBuildRequest`, `AppCleanRequest`, `AppCreateRequest`, `AppFlashRequest`,
`AppLockRequest`, `AppOutdatedRequest`, `AppSyncRequest`, `AppUpdateRequest`,
`AppViewRequest`, `AppRttRequest`, `BoardCreateRequest`, `ModuleChangeRequest`, `ModuleInitRequest`,
`ModuleRegisterRequest` and `ModuleUpdateRequest`.

## What comes back

Most operations return nothing and raise on failure. The ones with something to say return
a typed object rather than parsed text:

| Call | Returns |
| --- | --- |
| `create_app` | The `Path` of the app it created |
| `doctor` | A `DoctorReport` |
| `flash_app` | A `FlashResult` |
| `reset_target` | A `ResetResult` |
| `resolve_rtt_app` | Offline `RttSettings` without accessing probes |
| `rtt_app` | A `RttResult` with selected probe and byte count |
| `add_module`, `remove_module`, `update_modules` | A list of `ModuleChange` |
| `register_module` | One `ModuleChange` |

```python
from neuralspotx import doctor

report = doctor()
if not report.ok:
    for check in report.checks:
        if not check.ok:
            print(check.label, check.hint)
```

For bounded RTT channel 0 capture, use a typed request:

```python
from neuralspotx import AppRttRequest, resolve_rtt_app, rtt_app

request = AppRttRequest(app_dir=app_dir, probe_serial="123456789", duration_s=10)
settings = resolve_rtt_app(request)  # ELF address and configured device; no probe access
result = rtt_app(request, on_data=lambda data: print(repr(data)))
```

The callback receives bytes and must return promptly; its exceptions propagate
after worker cleanup. `request.capture` creates a new byte-exact file and retains
partial data on failure. The target must already run the firmware matching the
resolved executable. See [RTT capture](/neuralspotx/guides/apps/build-flash-view/#rtt-capture)
for installation and timing contracts.

## Errors

Catch `NSXError` to handle a configure or build tool failure in a Python workflow.
For example, a build matrix can record the failed board and continue:

```python
from neuralspotx import NSXError, build_app

try:
    build_app(app_dir, frozen=True)
except NSXError as exc:
    print(f"build failed: {exc}")
```

When CMake configure or the Ninja build exits unsuccessfully, `configure_app` and
`build_app` raise `NSXToolchainError`. Its message includes the command, exit code
and trailing tool output. The chained `subprocess.CalledProcessError` exposes the
argument list (`cmd`) and exit status (`returncode`). A subprocess that exceeds
`timeout_s` raises `NSXTimeoutError`. Exceptions from your build `on_line` callback
propagate to your code.

Catch a narrower type when you intend to handle a specific case. The ten exported types
are `NSXCacheError`, `NSXConfigError`, `NSXGitError`, `NSXIntegrityError`, `NSXLockError`,
`NSXModuleError`, `NSXResolutionError`, `NSXTimeoutError`, `NSXToolchainError` and the
`NSXError` base. `NSXIntegrityError` is the one a `--frozen` equivalent raises when the
tree has drifted from the lock.

## Progress output

Long operations accept an `emit` callable, which is how the CLI prints progress. Pass your
own to route events into a log. Omitting it (or passing `None`) uses the default
emitter: progress goes to stderr and line events to stdout. A no-op callback such as
`emit=lambda event: None` suppresses these events; it does not suppress every source of
output, such as separately configured subprocess or capture callbacks:

```python
from neuralspotx import build_app, default_emitter

build_app(app_dir, emit=default_emitter)
```

`build_app` and `flash_app` additionally take `on_line`, called once per line of compiler
output, which is what you want for streaming a build into a test report rather than
buffering it.

## Beyond the five commands

The exported surface is wider than the app lifecycle. It covers modules
(`list_modules`, `describe_module`, `search_modules`, `init_module`,
`validate_module_metadata`), locking (`lock_app`, `sync_app`, `outdated_app`,
`update_app`), the registry (`load_registry`, `starter_profile`,
`registry_module_project`), boards (`create_board`, `describe_board`), caches (`cache_info`, `clean_cache`),
SBOM generation (`generate_sbom`) and app discovery (`find_app_root`, `resolve_app_dir`).

`load_registry()` and `starter_profile()` return independent snapshots. You may edit
nested dictionaries and lists without changing later results or other callers' data.
These edits do not persist registry overrides; use app configuration for that.

`find_app_root` is the one to reach for first in a script: it reproduces the walk-up that
the CLI does, so your tool resolves an app the same way `nsx build` would.

## A build matrix

The case where the API is clearly better than shelling out:

```python
from neuralspotx import NSXError, build_app, configure_app

BOARDS = ["apollo510_evb", "apollo510b_evb", "apollo4p_blue_kxr_evb"]

for board in BOARDS:
    try:
        configure_app(app_dir, board=board, frozen=True)
        build_app(app_dir, board=board, frozen=True)
    except NSXError as exc:
        print(f"{board}: FAIL {exc}")
    else:
        print(f"{board}: ok")
```

Each board builds into its own directory, so the loop does not need to clean between
iterations. See
[Multi-target and portability](/neuralspotx/guides/concepts/multi-target/).

## For agents

An agent driving NSX should not parse help text. Two commands emit structured data
instead.

`nsx commands --json` returns the whole command tree: every command and subcommand, which
ones are aliases, and for each one its options with flags, destination, default, help
string and whether it is required. It is the machine-readable equivalent of walking every
`--help`.

```bash
nsx commands --json
```

`nsx doctor --json` returns the environment report as `{ok, checks[], notes}`, where each
check carries `label`, `ok`, `required`, `detail` and `hint`. That is enough to decide
whether a build can be attempted and what to tell a user if not.

Several module commands take `--json` too, including `nsx module list`,
`nsx module describe`, `nsx module validate` and `nsx outdated`. The module catalog is
also published as data at
[`/neuralspotx/modules/catalog.json`](/neuralspotx/modules/catalog.json).

For programmatic workflows, import the API. Use `find_app_root` and `resolve_app_dir`
for the same app resolution the CLI uses.
