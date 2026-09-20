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

Three flags are build-only: `--jobs` for parallelism, `--target` to build one explicit
CMake target, and `--update` to re-resolve constraints to upstream tip and re-vendor
before building.

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
script or a CI job, where nothing is there to press Ctrl-C.

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
