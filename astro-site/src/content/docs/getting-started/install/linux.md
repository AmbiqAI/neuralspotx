---
title: Install on Linux
description: The Linux column of the install steps, plus the optional armclang and ATfE toolchain setup for Linux.
---

The Linux commands live on the main [Install](/neuralspotx/getting-started/install/) page,
in the Linux tab of each step. Examples there are written for Debian, Ubuntu and Fedora;
adapt the package manager for other distributions.

In short:

```bash
sudo apt update
sudo apt install python3 python3-pip cmake ninja-build git
curl -LsSf https://astral.sh/uv/install.sh | sh
# Arm GNU toolchain: extract the official download and put its bin/ on PATH
# SEGGER J-Link: install the .deb or .rpm pack
uv tool install neuralspotx
nsx doctor
```

## Arm GNU toolchain from the package manager

Faster to install than the official download, but often several releases behind:

```bash
# Debian and Ubuntu
sudo apt install gcc-arm-none-eabi

# Fedora
sudo dnf install arm-none-eabi-gcc-cs arm-none-eabi-newlib
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

1. Download the Linux build from the
   [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
2. Extract it somewhere stable, for example `/opt/ATfE-22.1.0`.
3. Extract the matching `ATfE-newlib-overlay` on top of that same directory. NSX and
   `nsx doctor` both need the bundled `newlib.cfg`.
4. Point `ATFE_ROOT` at the install directory. ATfE does not need to be on `PATH`, because
   NSX invokes its binaries by absolute path.

   ```bash
   export ATFE_ROOT="/opt/ATfE-22.1.0"   # add to ~/.bashrc
   ```

Select it per command with `--toolchain atfe`.

## Next

[Check your environment](/neuralspotx/getting-started/doctor/) with `nsx doctor`.
