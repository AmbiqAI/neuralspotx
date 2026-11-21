---
title: Profile firmware with ITM PC sampling
description: Use nsx-perf, a J-Link probe, and orbtop to rank functions on a running Apollo510 EVB.
---

A PMU counter can tell you how many cycles a workload used. To find **where**
the CPU spent time, the Cortex-M DWT periodically samples the program counter
and sends the address through ITM over the SWO pin. This samples running code
without a breakpoint or a software interrupt for each observation. On the host,
`orbtop` maps received addresses to functions using the ELF for the running image.

## Prepare the profiling example

Use the [pmu_profiling example](https://github.com/AmbiqAI/neuralspotx/tree/main/examples/pmu_profiling)
from a checkout matching your NSX CLI. Work in a copy of the example. The
commands below run in its directory and target `apollo510_evb` with GCC.

1. Add `nsx-perf` to the existing `modules` list in `nsx.yml`. Add `nsx::perf`
   to the existing `target_link_libraries(pmu_profiling PRIVATE ...)` in
   `CMakeLists.txt`. After `add_executable`, add
   `target_compile_options(pmu_profiling PRIVATE -g)` to retain line information.
2. In `src/main.c`, include `"nsx_perf_profile.h"`. Keep the existing
   `nsx_itm_printf_enable()` call and enable sampling immediately after it:

   ```c
   nsx_itm_printf_enable();
   if (nsx_perf_enable_pcsamp() != 0) {
       return 1;
   }
   ```

   For a capture **without printf**, remove the output calls and use this
   sequence instead. In SDK 5.2.32 the first helper sets up the SWO pin and
   trace path; the second enables periodic PC samples in the DWT.

   ```c
   if (nsx_itm_pcsamp_enable() != 0 || nsx_perf_enable_pcsamp() != 0) {
       return 1;
   }
   ```

3. To focus on the workload, shorten the example's two-second delay to
   `nsx_delay_us(100)` for this measurement. Otherwise the delay can dominate
   the profile. Keep the original delay when that is the behavior you want to measure.
4. Refresh the lock after adding the module, then build:

   ```sh
   nsx lock
   nsx build --board apollo510_evb
   nsx probes
   ```

SDK 5.2.32 exposes these sampling helpers for Apollo510 and Apollo510B
(`AM_PART_APOLLO5B`), Apollo510 Lite (`AM_PART_APOLLO510L`), and Apollo330 Plus
(`AM_PART_APOLLO330P`). Other targets may support other parts of `nsx-perf`.
Use the same compile guards around the sampling calls in multi-SoC code.
The hardware run described here used Apollo510. [SDK capability and implementation](https://github.com/AmbiqAI/nsx-ambiq-sdk/blob/v5.2.32/modules/nsx-perf/src/nsx_perf_profile.c)

## Capture from the probe

Install the SEGGER J-Link GDB Server, Arm GNU GDB and objdump, and
[Orbuculum](https://github.com/orbcode/orbuculum) on the host. The command
examples use a POSIX shell and Orbuculum 2.2.0. The probe must have an SWO
connection to the target as well as SWD.

**Terminal 1 — start the server.** Set `APOLLO_PROBE` to the serial from
`nsx probes`. The Apollo510 EVB build resolves the device to `AP510NFA-CBR`;
check the effective `NSX_RESET_DEVICE` in this example's board build
`CMakeCache.txt` if you change targets. Use the console executable from your
SEGGER installation (`JLinkGDBServerCL.exe` on Windows).

```sh
JLinkGDBServerCLExe -select "USB=$APOLLO_PROBE" -device AP510NFA-CBR \
  -if SWD -speed 4000 -port 2331 -swoport 2332 -telnetport 2333 \
  -localhostonly 1 -singlerun -nogui
```

**Terminal 2 — program and run the matching ELF.** The following `load` replaces
the target firmware. The example's GCC output is an ELF named `pmu_profiling`
without a suffix. Leave GDB running after `continue`.

```sh
arm-none-eabi-gdb build/apollo510_evb/pmu_profiling
```

```gdb
target remote localhost:2331
monitor reset
load
monitor reset
monitor SWO start 0 1000000
continue
```

The last monitor command starts the probe's SWO receiver at the 1 MHz rate
used by this firmware. Use the rate configured for your target if it differs.
[SEGGER GDB Server reference](https://kb.segger.com/J-Link_GDB_Server)

**Terminal 3 — rank functions.** Connect to the server's **raw SWO port**
(2332 here). Select raw ITM decoding and point both host tools at the same ELF.
Use an app directory without spaces for Orbuculum 2.2.0's objdump invocation.

```sh
OBJDUMP=arm-none-eabi-objdump orbtop -p ITM -s localhost:2332 \
  -e build/apollo510_evb/pmu_profiling -c 8
```

Illustrative one-second interval from an Apollo510 EVB with the shortened
delay and printf enabled:

```text
 99.13%    17055 main
  0.28%       49 br_util_delay_cycles
  0.25%       44 am_util_stdio_vsprintf
  0.23%       41 am_hal_itm_print
```

GCC inlined the workload into `main` in this build. Add `-l` to the orbtop
command for source-line attribution. Percentages describe received samples;
inlining, time spent in delays, and SWO bandwidth affect what you see. They
are unsuitable as exact cycle counts.

## SWO ownership and teardown

Keep `nsx view` and the Cortex-Debug SWO viewer closed while collecting PC samples.
On the Apollo510 EVB, starting `nsx view --no-reset-on-open` on the same external
Apollo ICD still produced printf text, but the running orbtop session dropped
to zero PC samples. Closing the viewer alone did not restore the stream during
the observation. To recover, close the viewer, interrupt GDB, and repeat
`monitor reset`, `monitor SWO start 0 1000000`, and `continue` to rerun firmware
initialization. Check that named functions reappear.

If Cortex-Debug already owns the J-Link GDB server, use that server's raw SWO
port from the debug console instead of starting a second server. With the
firmware halted before trace initialization, issue the SWO monitor command
through GDB and resume. Leave IDE trace decoding disabled so orbtop can consume
the stream. To finish a CLI session, stop orbtop with Ctrl+C, interrupt GDB,
then enter `detach` and `quit`.
