---
title: Build, flash and view
description: How nsx configure, build, flash, reset and view behave day to day, including the reset policy and the flags worth knowing.
---

[Configure and build](/neuralspotx/getting-started/configure-and-build/) and
[Flash, reset and view](/neuralspotx/getting-started/flash-and-view/) walk the five
commands in order. This page is the working reference for their behavior: what each one
does when you run it repeatedly, how they find your app, and the few behaviors that
surprise people.

Full option tables are generated from the CLI itself and live under
[the CLI reference](/neuralspotx/reference/cli/).

## Which commands know about your app

`configure`, `build`, `flash`, `view` and `clean` find the app by walking up from your
working directory until they find an `nsx.yml`, so you can run them from anywhere inside
the tree. They all take `--app-dir` to point somewhere else, and all take a positional
`app` argument that resolves under `./` and `./examples`.

`reset` and `probes` are not app-aware. `probes` enumerates the J-Link probes attached to
the machine. `reset` talks to a target directly and requires `--device`, so the
app-directory framing does not apply to it.

## Configure

`nsx configure` resolves the module graph, writes `nsx.lock` if there is not one, syncs
`modules/` to match it, and runs CMake to generate `build/<board>/`.

It is safe to re-run. NSX re-configures on its own when `build.ninja` is missing or when
you pass `--probe-serial`, which always forces a reconfigure because the probe serial is
baked into the generated SEGGER command files.

## Build

`nsx build` configures first if no build tree exists, so on a fresh app `nsx build` alone
is enough. It drives Ninja through CMake and leaves the linked image, the `.bin` and the
`.map` in `build/<board>/`.

Configure also enables `compile_commands.json` in the selected build directory
for clangd and static-analysis tools. Each build keeps its own module inputs at
`<build-dir>/nsx/modules.cmake`, including when you choose a custom `--build-dir`.
After configuring board A and then board B, plain CMake reconfiguration of A
continues to use A's module list. Shared vendored sources still require normal
NSX lock/sync coordination; build-local inputs do not isolate dependency updates.

For an existing app, run `nsx configure` once for each build directory after
upgrading. If a build directory is missing its inputs, or its selected board does
not match them, the loader reports how to regenerate them. The existing
`cmake/nsx/modules.cmake` include remains the app entry point.

`--jobs`, `--target` and `--update` are accepted by both `build` and `flash`. `--jobs`
sets the parallelism. `--target` selects a CMake target to build, or an executable to
flash. `--update` re-resolves constraints to upstream tip and re-vendors first.

:::caution[`--sdk-root` and `--frozen` are mutually exclusive]
`--sdk-root` points the build at an SDK tree on your machine instead of the vendored one.
That tree is not recorded in `nsx.lock`, so the build is no longer reproducible from the
lock and NSX rejects the combination rather than producing a binary it cannot account for:

```text
--sdk-root (/opt/AmbiqSuite) cannot be combined with --frozen: ... Drop one of the two flags.
```
:::

## Flash

`nsx flash` builds if the image is missing or out of date, then drives the generated
SEGGER flash target.

NSX reads J-Link's own output to decide whether the program actually happened, looking for
either a `Flash download: Total` summary or a `Skipped. Contents already match` notice.
If J-Link exits successfully but prints neither, NSX tells you rather than assuming
success, because different J-Link Commander releases word the summary differently. The
device was most likely programmed; the echoed J-Link output above the message is what to
read.

`--probe-serial` selects one probe when several are attached. Run `nsx probes` to list
them.

## View

`nsx view` opens the SEGGER SWO viewer against the running firmware.

### The reset policy

By default `view` resets the target as it attaches, so you see output from the start of
`main`. Four SoCs are the exception and default to attaching without a reset:
`apollo3p`, `apollo4l`, `apollo4p` and `apollo510b`. On those, NSX says what it is doing:

```text
Using attach-only SWO view for this secure-reset SoC; flash first or pass --reset-on-open to force a reset.
```

This set is defined in the NSX source, not inferred from the SoC family name, so it does
not line up neatly with "all Apollo4" or "all secure parts". Override it either way with
`--reset-on-open` or `--no-reset-on-open`. `--reset-delay-ms` controls how long NSX waits
after the reset before reading, and defaults to 400.

### Capturing instead of watching

`--capture <path>` writes the stream to a file as well as the terminal, and `--duration
<seconds>` stops the viewer after a fixed time. Together they are what you want in a
script or a CI job, where no one is there to press Ctrl-C. Prefer `--duration` to wrapping
the command in `timeout`.

NSX stops the SEGGER viewer when the command ends: on Ctrl-C, when `--duration` expires,
and on an error. On Linux and macOS it also stops the viewer when `nsx` receives
`SIGTERM` or `SIGHUP`, as from `timeout`, `kill` or a canceled CI step, and then exits
with status 128 plus the signal number. On Linux the viewer also exits if `nsx` is killed
outright, and on Windows it is tied to `nsx` by a job object. A viewer left running would
hold the J-Link SWO port and block the next `nsx view` on any board.

## RTT capture

For firmware using `nsx-segger-rtt` (such as CoreMark), install the optional host
adapter and SEGGER J-Link Software, then capture channel 0:

```bash
pipx inject neuralspotx pylink-square
nsx configure --app-dir coremark
nsx build --app-dir coremark
nsx flash --app-dir coremark --probe-serial 123456789
nsx rtt --app-dir coremark --probe-serial 123456789 --duration 25 --file coremark.bin
```

A Python environment can instead install `neuralspotx[rtt]`. RTT requires an
already configured and built executable. `nsx rtt` never builds, flashes, or
explicitly resets the target. The ELF on disk must match the flashed firmware;
NSX cannot verify that identity from host artifacts. Reconfigure builds made by
older NSX versions to generate their target artifact pointers.

`--target` selects another executable; `--board` and `--build-dir` select its
configuration. CMake records the actual executable path, including GCC `.axf`
and ATFE/Arm Compiler `.elf` output. NSX reads `_SEGGER_RTT` from its ELF symbols.
A stripped binary or one without RTT produces an actionable error.

The serial precedence is explicit `--probe-serial`, configured serial, then the
only connected USB probe. Multiple probes require an explicit selection. Use
`nsx probes` to list them. NSX does not terminate another process holding a probe.

`--startup-timeout` defaults to 10 seconds and covers connection and channel
readiness. `--duration` defaults to 10 seconds and starts at readiness. Both
must be positive and finite. A private process contains native SEGGER calls;
shutdown gets three additional seconds before forced termination and an error.
Process termination may need a further short grace period. A ready but silent
channel returns zero bytes and a warning; it does not verify firmware output.

The terminal decodes UTF-8 with replacement for invalid bytes and characters
unavailable in its output encoding. `--file` (also
`--capture`) writes exact bytes to a **new** file; existing files are refused.
Partial captures remain on errors or interruption. API callers use
`AppRttRequest`, `resolve_rtt_app`, and `rtt_app`; a streaming callback receives
bytes synchronously and must return promptly. Slow callbacks or output sinks
can delay parent-side timeout enforcement.

Inspect resolved settings without enumerating probes or loading SEGGER:

```bash
nsx rtt --app-dir coremark --print-settings
```

The JSON includes executable, control-block address, device, interface, speed,
channel, and configured serial (or `null` if selection will happen at capture).
These values can also be entered into a standalone RTT viewer. Transport
selection in `nsx.yml` and automatic SWO/RTT cross-warnings are follow-up work in
[issue #148](https://github.com/AmbiqAI/neuralspotx/issues/148).

## Reset

`nsx reset --device <device>` resets a target without touching an app. The device name is
the J-Link device identifier for the part, which for a generated app appears as the
`-device` argument in `build/<board>/build.ninja`.

## Clean

```bash
nsx clean          # run the build system's clean target
nsx clean --full   # remove the build directory outright
nsx clean --reset  # also remove modules/ and .nsx/
```

`--reset` takes the app back to the state of a fresh clone, so the next `nsx configure`
re-fetches everything from `nsx.lock`. It prompts before discarding locally modified files
under `modules/`; `--force` skips the prompt.

## A working loop

```bash
nsx build          # compile
nsx flash          # build if needed, then program
nsx view           # watch SWO output
```

After the first configure, `nsx flash` on its own covers the common case: it builds what
changed and programs the result.

If something in that loop fails, [Troubleshooting](/neuralspotx/guides/apps/troubleshooting/)
is organized around the messages NSX actually prints.
