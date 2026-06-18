# Install on Linux

Platform tools for NSX on Linux. These are steps 1–3 of
[Install and Setup](index.md) — when you're done, return there to install
the CLI and run `nsx doctor`. Examples are shown for Debian/Ubuntu and
Fedora; adapt the package manager for other distributions.

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

=== "Debian / Ubuntu"

    ```bash
    sudo apt update
    sudo apt install python3 python3-pip cmake ninja-build git
    # uv (official installer):
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Fedora"

    ```bash
    sudo dnf install python3 python3-pip cmake ninja-build git
    # uv (official installer):
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## 2. Compiler Toolchain

GCC (the **Arm GNU Toolchain**) is the default and builds every example. You
only need one toolchain to get started. Distro packages are often several
years behind, so the official download gives you a current compiler:

1. Get the `arm-none-eabi` Linux build from the
   [Arm GNU Toolchain downloads](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads).
2. Extract it to a stable location, e.g. `/opt/arm-gnu-toolchain`.
3. Add its `bin/` to your `PATH`:

   ```bash
   echo 'export PATH="/opt/arm-gnu-toolchain/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

??? note "Quick alternative via the package manager"
    Faster to install, but may be older than 13.x:

    === "Debian / Ubuntu"

        ```bash
        sudo apt install gcc-arm-none-eabi
        ```

    === "Fedora"

        ```bash
        sudo dnf install arm-none-eabi-gcc-cs arm-none-eabi-newlib
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

    1. Download the Linux build from the
       [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
    2. Extract it to a stable location, e.g. `/opt/ATfE-22.1.0`.
    3. **Also extract the matching `ATfE-newlib-overlay` on top of that same
       directory** — NSX (and `nsx doctor`) require the bundled `newlib.cfg`.
    4. Point `ATFE_ROOT` at the install directory (ATfE does **not** need to be
       on `PATH` — NSX invokes its binaries by absolute path):

       ```bash
       export ATFE_ROOT="/opt/ATfE-22.1.0"   # add to ~/.bashrc
       ```

    See [Toolchain Support](../../architecture/toolchain-support.md) for
    build-flag and linker details.

## 3. Debug Probe (Optional)

A **SEGGER J-Link** is required to flash firmware (`nsx flash`) and stream live
SWO output (`nsx view`). The Apollo510 EVB includes an onboard J-Link.

Download the J-Link Software and Documentation Pack (`.deb` or `.rpm`) from
[SEGGER](https://www.segger.com/downloads/jlink/) and install it.

## Next Steps

Platform tools are in place — return to
[Install and Setup](index.md#4-install-the-nsx-cli) to install the `nsx` CLI
and verify with `nsx doctor`.
