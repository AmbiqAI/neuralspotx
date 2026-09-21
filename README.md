# neuralspotx

[![CI](https://github.com/AmbiqAI/neuralspotx/actions/workflows/ci.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/ci.yml)
[![Docs](https://github.com/AmbiqAI/neuralspotx/actions/workflows/docs.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/docs.yml)
[![Release](https://github.com/AmbiqAI/neuralspotx/actions/workflows/release.yml/badge.svg)](https://github.com/AmbiqAI/neuralspotx/actions/workflows/release.yml)

`neuralspotx` is the NSX tooling repo.

NSX is a lightweight bare-metal workflow for Ambiq targets. It provides:

- the `nsx` CLI
- packaged app templates
- packaged CMake helpers
- built-in board definitions
- curated metadata for module and SDK selection

The primary audience is app developers creating small, focused NSX applications
for bring-up, profiling, validation, and simple demos.

NSX is also the build-and-deploy vehicle for Ambiq's **Helia** AI stack:

- [heliaRT](https://github.com/AmbiqAI/helia-rt) — optimized LiteRT (TFLite
  Micro) runtime, shipped as an NSX module
- [heliaAOT](https://github.com/AmbiqAI/helia-aot) — ahead-of-time compiler that
  generates NSX modules from `.tflite` models
- [heliaPROFILER](https://github.com/AmbiqAI/helia-profiler) — on-device model
  profiler built on NSX

## Documentation

The documentation site is <https://ambiqai.github.io/neuralspotx/>: getting
started, guides, the module catalog, and a CLI, Python API and configuration
reference generated from the source. Agents can read
[`llms.txt`](https://ambiqai.github.io/neuralspotx/llms.txt) or any route's
`.md` rendition instead.

The site itself is an Astro project in `astro-site/`, published from `main` by
`.github/workflows/docs.yml`. To work on it:

```bash
cd <nsx-repo>
uv sync --group docs          # the reference is generated from the package
npm --prefix astro-site ci
npm --prefix astro-site run dev
npm --prefix astro-site run validate
```

Maintainer material that is not published lives in
[`docs/maintainers/`](docs/maintainers/): release mechanics, repo layout, board
and module coverage, design decisions, and how the docs site is built.

## Quick Start

NSX uses an app-first flow. Each app is a self-contained project directory with
vendored modules, board definitions, and build helpers.

For app users, the cleanest install path is `uv`, which `nsx doctor` already
requires:

```bash
uv tool install neuralspotx
nsx doctor
nsx create-app hello_ap510 --board apollo510_evb
```

`uvx --from neuralspotx nsx doctor` runs a single command without installing
anything. `pipx install neuralspotx` works too if you already manage your CLI
tools that way.

For contributors working from a source checkout:

```bash
cd <nsx-repo>
uv sync
source .venv/bin/activate
uv tool install pre-commit
pre-commit install
nsx doctor
nsx create-app hello_ap510 --board apollo510_evb
```

`pre-commit install` sets up the lint and pre-push hooks that CI also runs. See
[CONTRIBUTING.md](CONTRIBUTING.md) for what runs at each stage.

Build the app:

```bash
nsx configure --app-dir hello_ap510
nsx build --app-dir hello_ap510
```

## Repo Scope

This repo owns:

- `src/neuralspotx`
- packaged templates
- packaged board definitions
- CMake helper assets used by generated apps

Built-in firmware modules are described by the packaged registry and fetched
from their default upstream repos as needed. Normal app users create standalone
app directories and let NSX manage module resolution, vendoring, configuration,
build, flash, and view flows.
