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

NSX currently uses a workspace-first flow. Start by creating a workspace, then
generate apps inside it.

Initialize a workspace and create an app:

```bash
cd <nsx-repo>
uv sync
uv run nsx doctor
uv run nsx init-workspace <workspace>
uv run nsx create-app <workspace> hello_ap510 --board apollo510_evb
```

Build the app:

```bash
cd <nsx-repo>
uv run nsx configure --app-dir <workspace>/apps/hello_ap510
uv run nsx build --app-dir <workspace>/apps/hello_ap510
```

## Repo Scope

This repo owns:

- `src/neuralspotx`
- packaged documentation and templates
- packaged board definitions
- CMake helper assets used by generated apps

Built-in firmware modules are described by the packaged registry and fetched
from their default upstream repos as needed. Generated and reference apps live
in `nsx-apps/`.
