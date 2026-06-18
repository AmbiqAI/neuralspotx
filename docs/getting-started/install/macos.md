# Install on macOS

Platform tools for NSX on macOS, using [Homebrew](https://brew.sh). These
are steps 1–3 of [Install and Setup](index.md) — when you're done, return
there to install the CLI and run `nsx doctor`.

## 1. System Prerequisites

NSX generates CMake projects that cross-compile for Arm Cortex-M targets.
Install these host tools first:

| Tool | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Runs the NSX CLI and module resolver |
| **uv** | latest | Fast Python dependency management |
| **CMake** | 3.24+ | Build-system generator |
| **Ninja** | any | Parallel build backend |
| **Git** | any | Fetches module sources from their upstream repos |

```bash
brew install python uv cmake ninja git
```

## 2. Compiler Toolchain

GCC (the **Arm GNU Toolchain**) is the default and builds every example. You
only need one toolchain to get started.

```bash
brew install --cask gcc-arm-embedded
```

Verify the compiler is reachable:

```bash
arm-none-eabi-gcc --version
```

### Optional Toolchains

GCC is all most users need. NSX also supports two alternates — select either
with `--toolchain armclang` or `--toolchain atfe` on any build command.

??? note "Arm Compiler for Embedded (armclang) — 6.22+"
    A licensed commercial compiler (Arm Compiler 6). Install it from Arm,
    ensure `armclang` is on your `PATH`, and NSX detects it automatically. No
    environment variable is required.

??? note "Arm Toolchain for Embedded (ATfE) — experimental, 22.1+"
    ATfE is Arm's free LLVM-based bare-metal toolchain (clang + lld + picolibc
    with a newlib overlay).

    1. Download the macOS build from the
       [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
    2. Extract it to a stable location, e.g.
       `/Applications/ATFEToolchain/ATfE-22.1.0`.
    3. **Also extract the matching `ATfE-newlib-overlay` on top of that same
       directory** — NSX (and `nsx doctor`) require the bundled `newlib.cfg`.
    4. Point `ATFE_ROOT` at the install directory (ATfE does **not** need to be
       on `PATH` — NSX invokes its binaries by absolute path):

       ```bash
       export ATFE_ROOT="/Applications/ATFEToolchain/ATfE-22.1.0"   # add to ~/.zshrc
       ```

    See [Toolchain Support](../../architecture/toolchain-support.md) for
    build-flag and linker details.

## 3. Debug Probe (Optional)

A **SEGGER J-Link** is required to flash firmware (`nsx flash`) and stream live
SWO output (`nsx view`). The Apollo510 EVB includes an onboard J-Link.

```bash
brew install --cask segger-jlink
```

## Next Steps

Platform tools are in place — return to
[Install and Setup](index.md#4-install-the-nsx-cli) to install the `nsx` CLI
and verify with `nsx doctor`.
