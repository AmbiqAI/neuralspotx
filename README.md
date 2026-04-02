# neuralspotx

[![CI](https://github.com/AmbiqAI/neuralspotx/actions/workflows/ci.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/ci.yml)
[![Pages](https://github.com/AmbiqAI/neuralspotx/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/deploy-pages.yml)
[![Release Please](https://github.com/AmbiqAI/neuralspotx/actions/workflows/release-please.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/release-please.yml)

`neuralspotx` is the NSX tooling repo.

NSX is a lightweight bare-metal workflow for Ambiq targets. It provides:

- the `nsx` CLI
- packaged app templates
- packaged CMake helpers
- built-in board definitions
- curated metadata for module and SDK selection

The primary audience is app developers creating small, focused NSX applications
for bring-up, profiling, validation, and simple demos.

For contributor workflows such as releases, CI, and the Python API surface, use
the docs site under `docs/`.

## Documentation

The main documentation lives in the docs site built from `docs/`.

Install the docs toolchain:

```bash
cd <nsx-repo>
uv sync --group docs
```

Run the docs site locally:

```bash
cd <nsx-repo>
uv run --group docs zensical serve
```

Build the static site:

```bash
cd <nsx-repo>
uv run --group docs zensical build
```

## Quick Start

NSX uses an app-first flow. Each app is a self-contained project directory with
vendored modules, board definitions, and build helpers.

For app users, the cleanest install path is `pipx`:

```bash
pipx install git+https://github.com/AmbiqAI/neuralspotx.git
nsx doctor
nsx create-app hello_ap510 --board apollo510_evb
```

For contributors working from a source checkout:

```bash
cd <nsx-repo>
uv sync
source .venv/bin/activate
nsx doctor
nsx create-app hello_ap510 --board apollo510_evb
```

Build the app:

```bash
nsx configure --app-dir hello_ap510
nsx build --app-dir hello_ap510
```

## Repo Scope

This repo owns:

- `src/neuralspotx`
- packaged documentation and templates
- packaged board definitions
- CMake helper assets used by generated apps

Built-in firmware modules are described by the packaged registry and fetched
from their default upstream repos as needed. Normal app users create standalone
app directories and let NSX manage module resolution, vendoring, configuration,
build, flash, and view flows.
