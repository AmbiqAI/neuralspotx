# Install and Setup

Everything you need to go from a blank terminal to a working `nsx`
command — in about five minutes.

## Required Tools

NSX generates CMake projects that cross-compile for Arm Cortex-M targets.
Make sure the following are available on your `PATH`:

| Tool | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Runs the NSX CLI and module resolver |
| **uv** | latest | Fast Python dependency management |
| **CMake** | 3.24+ | Build-system generator |
| **Ninja** | any | Parallel build backend |
| **Arm GNU Toolchain** | 13.x+ | `arm-none-eabi-gcc` cross-compiler (default) |
| **SEGGER J-Link** | 7.x+ | Flash firmware and stream SWO output |

!!! tip
    On macOS you can install most of these with Homebrew:
    ```bash
    brew install python uv cmake ninja
    brew install --cask gcc-arm-embedded segger-jlink
    ```

## Optional Toolchains

NSX supports two additional cross-compilers alongside GCC. These are
**not** required — GCC is the default and works for all examples.

| Toolchain | Version | Setup |
|---|---|---|
| **Arm Compiler for Embedded (armclang)** | 6.22+ | Install and add to `PATH`. NSX detects `armclang` automatically. |
| **Arm Toolchain for Embedded (ATfE)** | 22.1+ | Install and set `ATFE_ROOT` to the install directory (tools are **not** on `PATH`). |

Use `--toolchain armclang` or `--toolchain atfe` with any `nsx` command
to select an alternate toolchain. See
[Toolchain Support](../architecture/toolchain-support.md) for details.

## Option A — Install with `pipx` (Recommended for App Developers)

If you just want the `nsx` CLI as a standalone tool:

```bash
pipx install git+https://github.com/AmbiqAI/neuralspotx.git
```

This gives you:

- The `nsx` CLI on your `PATH`
- All runtime Python dependencies in an isolated environment

Verify the install:

```bash
nsx --help
nsx doctor
```

`nsx doctor` checks your local toolchain — it will flag anything that's
missing or misconfigured before you try to build.

## Option B — Source Checkout (Recommended for Contributors)

Clone the repo and let `uv` handle the environment:

```bash
git clone https://github.com/AmbiqAI/neuralspotx.git
cd neuralspotx
uv sync
```

Activate the environment so `nsx` is available directly:

```bash
source .venv/bin/activate
nsx --help
```

Or, if you prefer not to activate, prefix every command with `uv run`:

```bash
uv run nsx doctor
```

## Verify the Installation

Regardless of install method, run the built-in environment check:

```bash
nsx doctor
```

A clean run means Python, CMake, Ninja, the Arm toolchain, and J-Link are
all reachable. Any missing tool is called out with a clear error message.

## Docs Tooling (Optional)

Working on the documentation site? Install the docs dependencies:

```bash
cd <nsx-repo>
uv sync --group docs
uv run --group docs zensical serve
```

## Next Steps

Environment is ready — time to [build your first app](first-app.md).
