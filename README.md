# neuralspotx

This repo is the NSX Python tooling repo.

It owns:
- the `nsx` CLI
- packaged app templates
- packaged CMake helpers
- registry and metadata handling

It does not aim to be the long-term home for firmware module repos.
Board definitions are now packaged with the tooling repo. Firmware modules
remain split out into a top-level sibling root:

- [`/Users/adampage/Ambiq/neuralspot/nsx-modules`](/Users/adampage/Ambiq/neuralspot/nsx-modules)
- [`/Users/adampage/Ambiq/neuralspot/nsx-apps`](/Users/adampage/Ambiq/neuralspot/nsx-apps)

## Current Layout

- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx): canonical Python package
- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/templates`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/templates): packaged app scaffolding
- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/cmake`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/cmake): packaged CMake helpers and SEGGER templates
- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/boards`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx/boards): packaged built-in board definitions
- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/docs`](/Users/adampage/Ambiq/neuralspot/neuralspotx/docs): architecture and bring-up notes

## Design Goals

- `nsx` is the primary user interface for create/build/flash/view/module management.
- Generated apps are standalone and vendor their own module and board content.
- Apps are single-target: one board, one SoC, one toolchain.
- AmbiqSuite-first baseline for bare-metal bring-up, with west and YAML used for dependency and workspace configuration.
- CMake is the build truth; legacy make flows are migration inputs only.
- Each major SDK line should map to explicit NSX modules and SoC support boundaries.

## Architecture docs

Architecture notes are tracked under:

- `docs/architecture/README.md`
- `docs/architecture/overview.md`
- `docs/architecture/module-model.md`
- `docs/architecture/metadata-model.md`
- `docs/architecture/sdk-provider-model.md`
- `docs/architecture/migration-from-monorepo.md`
- `docs/architecture/roadmap.md`

## Module layering

- SDK modules: `nsx-ambiqsuite-r3`, `nsx-ambiqsuite-r4`, `nsx-ambiqsuite-r5`
  - repo-backed local modules containing real AmbiqSuite payloads under `/Users/adampage/Ambiq/neuralspot/nsx-modules/nsx-ambiqsuite-r*/sdk`
- Release-specific SDK wrappers: `nsx-ambiq-hal-r*`, `nsx-ambiq-bsp-r*`
  - separate HAL and BSP build surfaces layered on top of the raw SDK payloads
- SoC HAL package: `nsx_soc_<soc>`
  - exports `nsx::soc_hal_apollo3p` or `nsx::soc_hal_apollo510`
- Board package: `nsx_board_<board>`
  - exports `nsx::board_apollo3p_evb` or `nsx::board_apollo510_evb`
- Core module packages: `nsx_core`, `nsx_harness`, `nsx_utils`, `nsx_peripherals`
  - export `nsx::core`, `nsx::harness`, `nsx::utils`, `nsx::peripherals`
- Core runtime package: `nsx_runtime_core`
  - exports `nsx::runtime_core`
- Optional package: `nsx_portable_api`
  - exports `nsx::portable_api`
- Tooling package: `nsx_tooling`
  - exports `nsx::tooling_helpers` and `nsx_add_segger_targets(...)`

## West-backed workspace bootstrap

Use a local `uv` environment in `neuralspotx` for reproducible west tooling:

```bash
cd neuralspotx
uv sync
uv run west --version
```

The `nsx` CLI is provided by the Python package at
[`/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx`](/Users/adampage/Ambiq/neuralspot/neuralspotx/src/neuralspotx).
It supports both CLI and library-style use.

Example workflow:

```bash
cd neuralspotx
uv run nsx init-workspace ~/ws/nsx-demo
uv run nsx create-app ~/ws/nsx-demo my_app --board apollo510_evb
uv run nsx sync ~/ws/nsx-demo
# alias:
uv run nsx new ~/ws/nsx-demo my_app2 --board apollo3p_evb
```

`create-app` emits `nsx.yml` in the app directory. This file is the app-local
module manifest used by `nsx module ...` commands. It also copies packaged CMake
support files into `cmake/nsx/`.

Module lifecycle commands:

```bash
cd ~/ws/nsx-demo/apps/my_app
uv run nsx module list
uv run nsx module add nsx-portable-api
uv run nsx module remove nsx-portable-api
uv run nsx module update
# Register an external module for this app only (no nsx package edit):
uv run nsx module register my-custom-module \
  --metadata /path/to/my-custom-module/nsx-module.yaml \
  --project my_custom_repo \
  --project-url https://github.com/myorg/my_custom_repo.git \
  --project-revision main \
  --project-path modules/my_custom_repo
# Local filesystem module project (no west-managed clone/update):
uv run nsx module register my-local-module \
  --metadata /path/to/my-local-module/nsx-module.yaml \
  --project my_local_repo \
  --project-local-path /abs/path/to/my-local-module
```

Workspace layout after `init-workspace`:

```text
<workspace>/
  manifest/west.yml
  neuralspotx/            # root NSX repo
  modules/                # west-managed external repos such as ambiqsuite
  apps/
```

Registry and module metadata:

- Curated lock registry: packaged in `neuralspotx.data/registry.lock.yaml`
- Per-module metadata file: `nsx-module.yaml` at each module root
- App-local external module overrides: `nsx.yml -> module_registry`
- Hard-fail compatibility checks enforce AmbiqSuite support + board/soc/toolchain compatibility.

Notes:
- `init-workspace` writes `manifest/west.yml`, runs `west init`, and optionally `west update`.
- Default NSX repo URL is the current local checkout (`file://...`) for easy local bring-up.
- You can pass remote URLs with `--nsx-repo-url` and `--ambiqsuite-repo-url`.
- If system `west` is not installed, run west commands through `uv run west ...` from `neuralspotx`.

## Smoke Test

The canonical hardware bring-up flow is documented here:

- [`/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/getting-started/ap510-smoke-test.md`](/Users/adampage/Ambiq/neuralspot/neuralspotx/docs/getting-started/ap510-smoke-test.md)

Standalone smoke apps live here:

- [`/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb`](/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo510_evb)
- [`/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo4p_evb`](/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo4p_evb)
- [`/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo3p_evb`](/Users/adampage/Ambiq/neuralspot/nsx-apps/smoke_apollo3p_evb)
