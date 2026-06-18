# Install on Windows

Platform tools for NSX on Windows, using
[winget](https://learn.microsoft.com/windows/package-manager/) and the
official Arm and SEGGER installers. These are steps 1–3 of
[Install and Setup](index.md) — when you're done, return there to install
the CLI and run `nsx doctor`.

!!! tip "Use a modern terminal"
    Run NSX from **PowerShell** or **Windows Terminal**.

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

```powershell
winget install Python.Python.3.12 astral-sh.uv Kitware.CMake Ninja-build.Ninja Git.Git
```

## 2. Compiler Toolchain

GCC (the **Arm GNU Toolchain**) is the default and builds every example. You
only need one toolchain to get started.

Download and run the official **Arm GNU Toolchain** Windows installer from the
[Arm GNU Toolchain downloads](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)
page. Check **"Add path to environment variable"** at the end of the installer.

Verify the compiler is reachable (open a new terminal first so the updated
`PATH` is picked up):

```powershell
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

    1. Download the Windows build from the
       [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
    2. Extract it to a stable location, e.g. `C:\ATfE-22.1.0`.
    3. **Also extract the matching `ATfE-newlib-overlay` on top of that same
       directory** — NSX (and `nsx doctor`) require the bundled `newlib.cfg`.
    4. Point `ATFE_ROOT` at the install directory (ATfE does **not** need to be
       on `PATH` — NSX invokes its binaries by absolute path):

       ```powershell
       setx ATFE_ROOT "C:\ATfE-22.1.0"
       ```

    See [Toolchain Support](../../architecture/toolchain-support.md) for
    build-flag and linker details.

## 3. Debug Probe (Optional)

A **SEGGER J-Link** is required to flash firmware (`nsx flash`) and stream live
SWO output (`nsx view`). The Apollo510 EVB includes an onboard J-Link.

Download and run the J-Link Software and Documentation Pack installer from
[SEGGER](https://www.segger.com/downloads/jlink/).

## Next Steps

Platform tools are in place — return to
[Install and Setup](index.md#4-install-the-nsx-cli) to install the `nsx` CLI
and verify with `nsx doctor`.
