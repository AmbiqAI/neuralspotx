---
title: Debug an NSX app in VS Code
description: Build and flash an Apollo510 app, stop at main with Cortex-Debug, and inspect peripheral registers using the device SVD.
---

Open the generated **app directory** in VS Code. This walkthrough uses the default
GCC app named `hello` on the Apollo510 EVB. You will program the board when you
start the flash task or launch the debugger.

## Prepare the app and probe

Install the [Cortex-Debug extension](https://marketplace.visualstudio.com/items?itemName=marus25.cortex-debug),
the Arm GNU toolchain (including GDB), and the SEGGER J-Link tools. Run
`nsx doctor` and check that `arm-none-eabi-gdb --version` and `nsx --version`
work in the environment used by VS Code tasks. See the [toolchain guide](/neuralspotx/guides/system/toolchains/).

```sh
nsx create-app hello --board apollo510_evb
cd hello
nsx configure --board apollo510_evb
nsx probes
```

Set `APOLLO_PROBE` to the USB serial printed for your probe in the environment
that starts VS Code (for example, `export APOLLO_PROBE=...` in a POSIX shell or
`$env:APOLLO_PROBE="..."` in PowerShell). Open the app with `code .` from that
environment. If VS Code is already running, restart it to pick up the value.
The task and Cortex-Debug both use this variable so that flashing and debugging
select the same probe even when several are connected.

For source-level stepping, add this line after `add_executable(hello ...)` in the
app's `CMakeLists.txt`. Applying the flags to the source file places them after
the SDK's release flags. The rest of the firmware keeps its normal optimization.

```cmake
set_property(SOURCE src/main.c APPEND PROPERTY COMPILE_OPTIONS -Og -g)
```

The configured Apollo510 board uses the SEGGER device `AP510NFA-CBR`. For
another target, inspect the board's `debug.cmake` and the SDK's SoC facts for
`NSX_SEGGER_DEVICE`; a board can override the SoC default. In this single-image
example the effective value also appears as `NSX_RESET_DEVICE` in the build's
`CMakeCache.txt`. Match the ELF to the executable produced by your app target.

NSX board metadata identifies the SoC. It currently supplies no SVD path.
For this board, download **AmbiqMicro.Apollo_DFP.1.5.2.pack** from the
[Arm pack catalog](https://www.keil.arm.com/packs/apollo_dfp-ambiqmicro/versions/).
Open the pack as a ZIP archive. Its `AmbiqMicro.Apollo_DFP.pdsc` maps
`AP510NFA-CBR` to `SVD/apollo510.svd`. Copy that member to
`debug/apollo510.svd` in your app. The debugger uses this XML file to display
register names and bit fields.

## Add the build and flash tasks

Save the following as `.vscode/tasks.json`. Use **Tasks: Run Build Task** to
build, or **Tasks: Run Task → NSX: flash** to build and program the image.

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "NSX: build",
      "type": "process",
      "command": "nsx",
      "args": ["build", "--app-dir", "${workspaceFolder}", "--board", "apollo510_evb"],
      "group": {"kind": "build", "isDefault": true},
      "problemMatcher": "$gcc"
    },
    {
      "label": "NSX: flash",
      "type": "process",
      "command": "nsx",
      "args": ["flash", "--app-dir", "${workspaceFolder}", "--board", "apollo510_evb",
               "--probe-serial", "${env:APOLLO_PROBE}"],
      "problemMatcher": "$gcc"
    }
  ]
}
```

## Launch and inspect the target

Save this as `.vscode/launch.json`. The pre-launch task programs the image through
NSX. Cortex-Debug then resets the target, uses the matching ELF for symbols, and
runs to `main`. On this GCC build the ELF is named `hello` without a suffix.

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug hello on Apollo510",
      "type": "cortex-debug",
      "request": "launch",
      "servertype": "jlink",
      "interface": "swd",
      "device": "AP510NFA-CBR",
      "serialNumber": "${env:APOLLO_PROBE}",
      "cwd": "${workspaceFolder}",
      "executable": "${workspaceFolder}/build/apollo510_evb/hello",
      "svdFile": "${workspaceFolder}/debug/apollo510.svd",
      "preLaunchTask": "NSX: flash",
      "overrideLaunchCommands": ["monitor reset"],
      "runToEntryPoint": "main"
    }
  ]
}
```

1. End any existing `nsx view` session so it releases the probe. Keep one
   owner of SWO during a debug or profiling session.
2. In **Run and Debug**, choose **Debug hello on Apollo510** and press **F5**.
   When the editor stops at `main`, use **Step Over (F10)** to advance a source line.
3. In the debug sidebar open the peripheral viewer (**Cortex Peripherals** in
   Cortex-Debug 1.10). Expand **MCUCTRL → CHIPPN** to inspect the chip part
   number while halted. If the peripheral list is empty, check `svdFile` and
   that the SVD belongs to this SoC.
4. Stop debugging before running another flash task or starting `nsx view`.
