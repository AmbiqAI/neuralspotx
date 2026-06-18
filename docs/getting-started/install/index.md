# Install and Setup

Everything you need to go from a blank terminal to a working `nsx`
command — in about five minutes.

The setup has four parts:

1. **System prerequisites** — Python, `uv`, CMake, Ninja, Git
2. **Compiler toolchain** — Arm GNU Toolchain (GCC) by default
3. **Debug probe** — SEGGER J-Link (only needed to flash and view on hardware)
4. **The `nsx` CLI** — installed with `pipx`

Then `nsx doctor` checks the installed tools and reports anything missing.

!!! tip "No board yet?"
    You don't need hardware to start. `nsx configure` and `nsx build` work
    with no probe attached — only `nsx flash` and `nsx view` need a connected
    EVB. You can skip the J-Link step until you have a board, but `nsx doctor`
    will still report J-Link as missing until it is installed.

## Choose Your Platform

Steps 1–3 (host tools, compiler, debug probe) are platform-specific. Follow
the guide for your OS, then come back here for the CLI install and the
`nsx doctor` check.

<div class="grid cards" markdown>

- :material-apple: **[macOS](macos.md)**

    ---

    Homebrew-based setup for Apple silicon and Intel Macs.

- :material-linux: **[Linux](linux.md)**

    ---

    Debian/Ubuntu and Fedora, with official Arm toolchain downloads.

- :material-microsoft-windows: **[Windows](windows.md)**

    ---

    `winget` plus the official Arm and SEGGER installers.

</div>

## 4. Install the `nsx` CLI

The CLI install is the same on every platform. For app developers, the
cleanest option is [`pipx`](https://pipx.pypa.io) — it puts `nsx` on your
`PATH` in an isolated environment:

If you do not already have `pipx`, install it first:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
```

Open a new terminal after `ensurepath`, then install `neuralspotx`:

```bash
pipx install neuralspotx
```

To pin a specific published version:

```bash
pipx install 'neuralspotx==<version>'
```

??? note "Prefer a source checkout? (contributors)"
    Clone the repo and let `uv` manage the environment:

    ```bash
    git clone https://github.com/AmbiqAI/neuralspotx.git
    cd neuralspotx
    uv sync
    ```

    Then either activate the venv (`source .venv/bin/activate`) so `nsx` is on
    your `PATH`, or prefix commands with `uv run` (e.g. `uv run nsx doctor`).

## Verify with `nsx doctor`

Whatever install path you chose, confirm your environment:

```bash
nsx doctor
```

`doctor` checks each prerequisite and prints a clear pass/fail per tool. A
fully provisioned host looks like:

```text
Python              ✓
uv                  ✓
cmake               ✓
ninja               ✓
git                 ✓
arm-none-eabi-gcc   ✓
  (armclang toolchain not detected — optional)
  (ATfE not detected — optional)
J-Link              ✓
```

The Arm GNU toolchain and SEGGER J-Link tools are required for the complete
flash/view workflow; armclang and ATfE are optional and only reported when
detected. If you intentionally skipped J-Link because you do not have hardware
yet, expect the SEGGER checks to fail until you install it. Each failing check
includes a hint describing what to install.

## Docs Tooling (Optional)

Working on the documentation site? Install the docs dependencies:

```bash
cd <nsx-repo>
uv sync --group docs
uv run --group docs zensical serve
```

## Next Steps

Environment is ready — time to [build your first app](../first-app.md).
