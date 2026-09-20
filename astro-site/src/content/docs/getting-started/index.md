---
title: Getting started
description: Install the NSX CLI, check your environment, and build and flash your first Ambiq board app.
---

NSX is installed once and then used per app. After `pipx install neuralspotx`, `nsx doctor`
checks the things a firmware build needs (Python, CMake, Ninja, the Arm toolchain and
SEGGER J-Link) and tells you which are missing before a build or a flash fails on them.

From there every app follows the same lifecycle: `nsx create-app` scaffolds a project
against a real board, `nsx configure` resolves its module dependencies and generates the
CMake tree, `nsx build` compiles and links the image, and `nsx flash` and `nsx view`
program the board and stream its output back. You can run `configure` and `build` without
hardware; only `flash` and `view` need a probe attached.

:::note[This section is still being filled in]
The install guides, the environment check, the first-app walkthrough and the migration
notes from neuralSPOT are being moved here from the MkDocs site in
[#260](https://github.com/AmbiqAI/neuralspotx/issues/260).
:::
