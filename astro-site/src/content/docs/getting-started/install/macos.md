---
title: Install on macOS
description: The macOS column of the install steps, plus the optional armclang and ATfE toolchain setup for macOS.
---

The macOS commands live on the main [Install](/neuralspotx/getting-started/install/) page,
in the macOS tab of each step. Everything there uses [Homebrew](https://brew.sh) and works
on Apple silicon and Intel.

In short:

```bash
brew install python uv cmake ninja git
brew install --cask gcc-arm-embedded
brew install --cask segger-jlink
pipx install neuralspotx
nsx doctor
```

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

1. Download the macOS build from the
   [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
2. Extract it somewhere stable, for example `/Applications/ATFEToolchain/ATfE-22.1.0`.
3. Extract the matching `ATfE-newlib-overlay` on top of that same directory. NSX and
   `nsx doctor` both need the bundled `newlib.cfg`.
4. Point `ATFE_ROOT` at the install directory. ATfE does not need to be on `PATH`, because
   NSX invokes its binaries by absolute path.

   ```bash
   export ATFE_ROOT="/Applications/ATFEToolchain/ATfE-22.1.0"   # add to ~/.zshrc
   ```

Select it per command with `--toolchain atfe`.

## Next

[Check your environment](/neuralspotx/getting-started/doctor/) with `nsx doctor`.
