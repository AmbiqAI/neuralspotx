# Install and Setup

This page covers the baseline environment needed for NSX app development.

## Required Tools

Install or make available in `PATH`:

- Python 3.10 or newer
- `uv`
- CMake
- Ninja
- Arm GNU toolchain
- SEGGER J-Link tools for flash and SWO view

If you plan to use workspace syncing, also make sure `west` is available. The
recommended way is to run it through the NSX environment.

## Set Up the NSX Environment

```bash
cd <nsx-repo>
uv sync
```

This installs:

- the `nsx` CLI from the local repo
- runtime Python dependencies
- `west`

Verify the CLI:

```bash
cd <nsx-repo>
uv run nsx --help
```

Run the built-in environment check:

```bash
cd <nsx-repo>
uv run nsx doctor
```

Verify `west`:

```bash
cd <nsx-repo>
uv run west --version
```

## Docs Tooling

If you are working on the docs site:

```bash
cd <nsx-repo>
uv sync --group docs
uv run --group docs zensical serve
```

## What You Need Next

After the environment is ready:

1. run `nsx doctor` to check the local toolchain setup
2. initialize a workspace with `nsx init-workspace`
3. generate an app with `nsx create-app`
4. configure and build it with `nsx configure` and `nsx build`
