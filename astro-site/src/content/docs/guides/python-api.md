---
title: Python API guide
description: Drive NSX from Python instead of the shell, handle its results and errors, and give an agent a machine-readable view of the CLI.
---

Everything the CLI does is a thin wrapper over a Python API, and the package exports that
API deliberately. Use it when you want a build matrix, a bring-up script, a test harness,
or NSX wired into a larger tool.

Every public symbol and signature is in the generated
[Python API reference](/neuralspotx/reference/api/). This page is how to start and what to
watch for.

:::note[The public API is provisional]
All 80 exported names are marked provisional: public and supported, but able to change in
a minor release. Pin your NSX version if you depend on them.
:::

## The shape of it

```python
from pathlib import Path
from neuralspotx import build_app, configure_app, create_app

app_dir = create_app(Path("hello_ap510"), board="apollo510_evb")
configure_app(app_dir)
build_app(app_dir)
```

Three conventions run through the whole surface:

- **The app directory is the first positional argument**, and every function accepts a
  path or a request object in that position.
- **Everything else is keyword only.** There are no positional option arguments to get in
  the wrong order.
- **Failure raises.** Nothing returns an error code you can ignore.

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

There is a request type per operation. Fifteen are exported: `AppActionRequest`,
`AppBuildRequest`, `AppCleanRequest`, `AppCreateRequest`, `AppFlashRequest`,
`AppLockRequest`, `AppOutdatedRequest`, `AppSyncRequest`, `AppUpdateRequest`,
`AppViewRequest`, `BoardCreateRequest`, `ModuleChangeRequest`, `ModuleInitRequest`,
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

## Errors

Everything NSX raises derives from `NSXError`, so one `except` clause is enough to catch
any NSX failure and let real bugs through:

```python
from neuralspotx import NSXError, build_app

try:
    build_app(app_dir, frozen=True)
except NSXError as exc:
    print(f"build failed: {exc}")
```

Catch a narrower type when you intend to handle a specific case. The ten exported types
are `NSXCacheError`, `NSXConfigError`, `NSXGitError`, `NSXIntegrityError`, `NSXLockError`,
`NSXModuleError`, `NSXResolutionError`, `NSXTimeoutError`, `NSXToolchainError` and the
`NSXError` base. `NSXIntegrityError` is the one a `--frozen` equivalent raises when the
tree has drifted from the lock.

## Progress output

Long operations accept an `emit` callable, which is how the CLI prints progress. Pass your
own to route it into a log, or leave it out to stay silent:

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
`registry_module_project`), boards (`create_board`), caches (`cache_info`, `clean_cache`),
SBOM generation (`generate_sbom`) and app discovery (`find_app_root`, `resolve_app_dir`).

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

For anything beyond inspection, import the API rather than shelling out. You get typed
results and typed exceptions instead of exit codes and text, and `find_app_root` and
`resolve_app_dir` give you the same app resolution the CLI uses.
