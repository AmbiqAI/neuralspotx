---
title: Install on Windows
description: The Windows column of the install steps, plus the optional armclang and ATfE toolchain setup for Windows.
---

The Windows commands live on the main
[Install](/neuralspotx/getting-started/install/) page, in the Windows tab of each step.
Run NSX from PowerShell or Windows Terminal.

In short:

```plaintext
winget install Python.Python.3.12 astral-sh.uv Kitware.CMake Ninja-build.Ninja Git.Git
# Arm GNU toolchain: run the official installer, tick "Add path to environment variable"
# SEGGER J-Link: run the J-Link Software and Documentation Pack installer
pipx install neuralspotx
nsx doctor
```

:::caution[Windows steps are unverified]
Every command in this section was executed on macOS. The Windows steps are carried over
from the previous documentation and have not been re-run on a Windows host, so treat the
winget package identifiers and the installer wording as unverified for now.
:::

## Optional toolchains

GCC builds every packaged example. Both alternates below are optional, and `nsx doctor`
reports them only when it finds them.

### Arm Compiler for Embedded (armclang)

A licensed commercial compiler. Install it from Arm, make sure `armclang` is on your
`PATH`, and NSX picks it up. No environment variable is needed. Select it per command with
`--toolchain armclang`.

### Arm Toolchain for Embedded (ATfE)

ATfE is Arm's LLVM based bare-metal toolchain (clang, lld and picolibc with a newlib
overlay). NSX treats it as experimental.

1. Download the Windows build from the
   [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
2. Extract it somewhere stable, for example `C:\ATfE-22.1.0`.
3. Extract the matching `ATfE-newlib-overlay` on top of that same directory. NSX and
   `nsx doctor` both need the bundled `newlib.cfg`.
4. Point `ATFE_ROOT` at the install directory. ATfE does not need to be on `PATH`, because
   NSX invokes its binaries by absolute path.

   ```plaintext
   setx ATFE_ROOT "C:\ATfE-22.1.0"
   ```

Select it per command with `--toolchain atfe`.

## Next

[Check your environment](/neuralspotx/getting-started/doctor/) with `nsx doctor`.
