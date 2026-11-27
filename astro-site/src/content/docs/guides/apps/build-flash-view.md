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

For VS Code build and flash tasks, source stepping and peripheral inspection, see
[Debug an NSX app in VS Code](/neuralspotx/guides/apps/debug-vscode/).

## Which commands know about your app

`configure`, `build`, `flash`, `view` and `clean` find the app by walking up from your
working directory until they find an `nsx.yml`, so you can run them from anywhere inside
the tree. They all take `--app-dir` to point somewhere else, and all take a positional
`app` argument that resolves under `./` and `./examples`.

`reset` uses the app's prepared primary target unless you supply `--device`.
`view` retains the executable named by `project.name`, even when the configured
reset primary is a different target. Register that executable for SWO use.
With `--device`, reset ignores app selectors. `probes` lists the attached J-Link
inventory without selecting a target.

| Operation | Target input | Host tool and transport |
| --- | --- | --- |
| Flash | Built binary and board load address | J-Link Commander over SWD |
| App reset | Configured primary target and verified connection settings | J-Link Commander over SWD |
| SWO view | CPU and trace clocks, SWO wiring, firmware emitting ITM data | SEGGER SWO Viewer over the SWO trace pin; reset-on-open also uses Commander over SWD |
| RTT capture | Matched ELF with the RTT control block, running firmware | pylink and the J-Link library reading target RAM over SWD |

A build-only board can configure and link firmware. Each physical operation also
requires support from its configured target and execution tool. Arm FVP targets
use `nsx run`. The physical implementation shipped with NSX uses a local USB J-Link.

## Configure

`nsx configure` resolves the module graph, writes `nsx.lock` if there is not one, syncs
`modules/` to match it, and runs CMake to generate `build/<board>/`.

An explicit `configure --probe-serial SERIAL` saves a preference for this build;
`configure` without a serial deliberately clears it. Implicit reconfiguration
preserves the validated preference. Successful configure prepares the debug context
when the app has adopted the handoff below; legacy build-only apps remain supported.

For flash, view, reset and RTT, `--probe-serial` is a temporary exact selection.
Omitting it inherits the selected target's configured preference; with no preference,
NSX requires exactly one eligible local USB probe. `--discover-probe` ignores the
preference for this operation. These flags are mutually exclusive. Selection occurs
once, including viewer/reset and reconnect, and never falls back to another probe.
`--frozen` verifies locked inputs before configure, Ninja regeneration and preparation,
even when a build directory already exists.

## Build

`nsx build` configures first if no build tree exists, so on a fresh app `nsx build` alone
is enough. It drives Ninja through CMake and leaves the linked image, the `.bin` and the
`.map` in `build/<board>/`.

Configure also enables `compile_commands.json` in the selected build directory
for clangd and static-analysis tools. Prepared apps store each board's resolved
module inputs at `cmake/nsx-resolved/<board>/modules.cmake`. Both NSX and direct
CMake use that snapshot. Each build retains its own `NSX_BOARD` selection;
preparing board B does not switch board A's module list. Vendored sources are
shared, so separate build directories do not isolate dependency updates.

### Build without installing NSX

A bootstrapped app created with current NSX, or an existing app prepared with
`nsx lock` followed by `nsx sync`, can be built with standard CMake commands.
For multiple targets, prepare each board with `nsx configure --frozen --board <board>`.
The recipient needs CMake 3.24 or newer, Ninja, and the selected compiler:

```sh
cmake -S . -B build/standalone -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/nsx/toolchains/arm-none-eabi-gcc.cmake \
  -DCMAKE_BUILD_TYPE=Release -DNSX_BOARD=apollo510_evb
cmake --build build/standalone
```

Replace the board with your app's prepared target. CMake warns if the compiler
family is outside the modules' declared compatibility. This preserves existing
explicit `nsx --toolchain` override behavior; a successful build does not qualify
an undeclared compiler. NSX dependency resolution still enforces the toolchain
specified in the manifest. Custom CMake options remain per-build cache settings.
The NSX Python package and virtual environment are not needed. NSX C/CMake
libraries and helper files remain local dependencies; no eject operation is needed.
Existing app CMake files and user presets are not rewritten.

Share the **complete prepared app directory**, including `modules/`, `boards/`,
`cmake/nsx/`, and `cmake/nsx-resolved/`, plus application files, manifests,
licenses and provenance. Exclude old build directories and virtual environments.
Several required directories are Git-ignored: a Git archive or ordinary clone
alone is not a complete offline bundle. `--no-bootstrap` apps must acquire and
prepare their dependencies first.

Changing dependency declarations requires `nsx lock` then `nsx sync`. Direct
CMake checks declaration bytes (including comments), notices metadata additions
and removals, and triggers reconfiguration on metadata changes during builds.
Application and library sources remain editable. A changed lock invalidates that
board's prepared snapshot until sync completes. Direct builds use the prepared
snapshot; they do not parse the lock, verify every source against its content hash,
or offer the integrity guarantees of `nsx sync --frozen`.

Old apps retain build-local inputs until upgraded with the current tool using
`nsx lock` and `nsx sync`. Frozen sync preserves pinned CMake tooling; it does not
upgrade an old loader. On prepared apps, manifest drift cannot be silently blessed
by a non-frozen sync: refresh the lock before building.

Offline portability assumes dependencies and generated assets are actually local.
External SDK overrides and symlinks pointing outside the app remain development
inputs and must be removed or supplied separately before sharing. Third-party
module CMake may require additional generators or downloads; this workflow does
not certify arbitrary module code as offline-safe. There is no archive/export
command yet.

Configured SEGGER targets can also be called directly, for example
`cmake --build build/standalone --target <app>_flash`. Set `NSX_JLINK_SERIAL`
explicitly when selecting a probe. SEGGER installation, valid board debug settings
and hardware qualification are still required.

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
them. Discovery failures (including a timeout, failed Commander process, or an
unrecognized response) produce an error, not an empty inventory. An empty result
means Commander completed a recognized enumeration with no probes. RTT preserves
discovery diagnostics received before its overall startup deadline; otherwise it
reports a startup timeout. The default RTT startup budget is 10 seconds, shorter
than discovery's 15-second timeout. An explicitly selected RTT serial still connects
directly without enumeration.

### External Apollo ICD

The standalone Apollo ICD uses the same SEGGER path as an EVB's onboard probe.
No NSX plugin or special board variant is needed: keep the target board selection
and pass the ICD's serial from `nsx probes` to both `flash` and `view`.

For the Apollo510 EVB, power the board through J16 USB with SW4 on, and connect
the ICD to **J2 DEBUG HDR**, matching the ribbon cable's pin-1 orientation.
The ICD needs its own USB connection and does not power the target. The EVB
requires no jumper changes for the external debugger; see
[SEGGER's Apollo510 EVB connection guide](https://kb.segger.com/AmbiqMicro_Apollo510_EVB).
For other boards or adapters, check their debug-header pinout before connecting.

For an SWO hello-world smoke test:

```sh
nsx probes
nsx create-app icd-smoke --board apollo510_evb
# Replace 123456789 with the external ICD's serial, not the onboard probe's.
nsx flash icd-smoke --probe-serial 123456789
nsx view icd-smoke --probe-serial 123456789 --no-reset-on-open \
  --duration 8 --capture icd-swo.txt
```

The default app prints repeatedly over SWO. `--no-reset-on-open` attaches to the
app that flash already started. A blinky app (`--template blinky`) instead toggles
the first BSP LED; on this EVB it is physical LED2, nearest the board's interior.
The stock blinky template does not print SWO messages.

This path was hardware-verified with NSX 0.9.6 and SEGGER J-Link 9.50 on an
Apollo510 EVB: application programming and verification succeeded, and a blinky
app with added SWO counter output produced consecutive counter values through
the external ICD. This does not qualify other boards or header adapters.

If the ICD enumerates but SWD cannot connect, check target power and cable seating
and orientation. A detected reference voltage alone does not establish a working
SWD connection. J-Link's probe product name describes the debugger, not the
connected target SoC.

## View

`nsx view` opens the SEGGER SWO viewer against the running firmware.

### The reset policy

NSX selects the SoC from the same app-local or packaged board descriptor as the build.
By default `view` resets the target as it attaches, so you see output from the start of
`main`. Four SoCs are the exception and default to attaching without a reset:
`apollo3p`, `apollo4l`, `apollo4p` and `apollo510b`. On those, NSX says what it is doing:

```text
Using attach-only SWO view for this secure-reset SoC; flash first or pass --reset-on-open to force a reset.
```

This set is defined in the NSX source, not inferred from the SoC family name, so it does
not line up neatly with "all Apollo4" or "all secure parts". Override it either way with
`--reset-on-open` or `--no-reset-on-open`. `--reset-delay-ms` controls how long NSX waits
between launching the viewer and issuing the optional reset. The default is 400 ms.
Attach-only mode skips that delay.

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
These values can also be entered into a standalone RTT viewer.

## Declare the primary console

An optional declaration in `nsx.yml` lets NSX warn when your selected command
uses a different transport:

```yaml
console:
  transport: rtt
  rtt_channel: 0
```

Keep `schema_version: 2`. This describes firmware intent; it does not configure
firmware, identify the flashed image, or automatically switch transports.
`nsx view` still uses SWO with its documented reset policy; `nsx rtt` remains
attach-only. Mismatches warn and continue. Missing metadata produces no warning.

Set `targets.supported.<board>.console` to replace the app declaration for a board.
Omission inherits; `console: null` clears it to unknown. A null board entry inherits.
Legacy single-board manifests use the app declaration. Explicit boards without an
override also use the app default. `transport` accepts `swo` or `rtt`; RTT accepts
only integer channel `0` (the default). SWO must omit `rtt_channel`. Empty mappings,
unknown fields, and unsupported values fail validation.

Declarations describe the primary executable named by `project.name`. RTT
`--target` selecting another executable does not use this declaration for warnings.
Warnings go to stderr; `--print-settings` remains JSON and capture files contain
only RTT bytes. Python callers can collect structured warnings with the optional
`emit` callback on `resolve_rtt_app` and `rtt_app`.

Older NSX versions may preserve but ignore console declarations. The declaration
is advisory, so older versions simply omit these warnings.

## Reset

`nsx reset --device <device>` resets a target without touching an app. The device name is
the J-Link device identifier for the part, which for a generated app appears as the
`-device` argument in `build/<board>/build.ninja`.

## Clean

```bash
nsx clean          # run the build system's clean target
nsx clean --full   # remove the selected, configured build directory
nsx clean --reset  # remove owned builds and restorable locked module copies
```

NSX records ownership when it initializes an empty build directory. Full clean checks
that record and the source directory, build directory and board recorded by CMake.
For an out-of-tree build, pass its path with `--build-dir`. If a build predates the ownership
record or was initialized in a nonempty directory, inspect the directory before removing it manually.

Reset checks the app's conventional build locations and all board sections in
`nsx.lock`. It preserves vendored and local source, unrecognized directories,
and the advisory lock in `.nsx/`. Missing, partial or stale receipts leave dependencies
in place. If a restorable copy under `modules/` differs from its locked hash,
reset stops before removing anything. Save the edits or rerun with `--force`
to discard edits to identified dependencies. Use `nsx sync --frozen` to restore
the default board's copies at their recorded revisions. For a different board, run
`nsx configure --board <board> --frozen`.

Recursive cleanup checks SDK overrides recorded in the app’s conventional build
directories. If an out-of-tree build selects an SDK inside the app, pass that build
with `--build-dir` during reset so NSX can read its cache. If an override overlaps a cleanup
location, NSX preserves the SDK source and the build that records its location.
Reconfigure with the SDK in a separate source directory to reclaim those builds.

Reset and full clean coordinate with lock, sync and update through the app writer
lock. Finish builds, debugger sessions and standalone CMake commands using the
affected directories before running cleanup.

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

## Configured debug handoff and existing apps

NSX app flash, SWO, reset and RTT require this handoff. Legacy helpers or disabled
handoffs fail with adoption instructions rather than executing older persistent
serial semantics. Direct CMake flash/reset/view targets remain available with their
configured defaults, including their existing custom-recipe behavior.

It requires CMake 3.31 or newer, single-configuration Ninja and updated app-local
NSX helpers. Build-only and direct CMake workflows retain their existing requirements.
New default/blinky apps enable it for Apollo510 EVB/GCC. Other boards, toolchains and
module graphs require an author audit and explicit adoption; the contract marker is
not automatic dependency certification. For an existing app, explicitly update the
vendored helpers and lock first (never through a frozen debug operation), then declare
`NSX_DEBUG_CONTEXT=ON` and `NSX_DEBUG_INPUT_CONTRACT=1` before including helpers.
Identify its primary debug target after registration:

```cmake
nsx_debug_set_primary_target(my_app)
```

New app templates already do this when the handoff is enabled. Custom apps
must name exactly one target registered by `nsx_add_segger_targets`. Audit reads
that influence debug settings before accepting the input contract. External
textual settings must use a registered read, for example:

```cmake
nsx_debug_read_text(PATH "${CMAKE_SOURCE_DIR}/device.txt" OUT NSX_SEGGER_DEVICE)
```

Use this before registering the target. The file's exact text becomes the
value, so do not include a trailing newline in a device-name file. Arbitrary
unregistered file/environment/network dependencies are not tracked. Recursive,
relative and symlink-following configuration globs are not supported initially.

After the app's normal standalone configuration, enable and explicitly prepare
(the example assumes vendored helpers at `cmake/nsx`):

```bash
cmake -S . -B build -DNSX_DEBUG_CONTEXT=ON -DNSX_DEBUG_INPUT_CONTRACT=1
cmake -DNSX_DEBUG_BUILD_DIR="$PWD/build" -P cmake/nsx/nsx_debug_prepare.cmake
```

Preparation configures three times and produces `build/nsx-debug/context.json`.
No firmware build or probe connection occurs. Any ordinary reconfiguration
invalidates it; failed preparation leaves no usable prior context. Repeat
preparation after changing configuration inputs. Keep input files and the build
directory unchanged while preparing or capturing an operation; simultaneous
build/configure/clean is unsupported. Ordinary C source edits do not invalidate
connection settings, but flashing still requires a successful build.

Literal paths containing glob characters (`*?[]`), quotes, semicolons or control
characters are unsupported by
this protocol; output artifacts must be inside the build tree.
Captured flash recipes support the existing single-image command sequence only:
`ExitOnError 1`, `Reset`, `LoadFile`, `Reset`, `Go`, `Exit` (full-line comments
and blank lines are allowed). The load command must reference the private binary copy and
the recorded address. Other commands or file references are rejected; direct
CMake recipes are unchanged. Captured SWO reset recipes likewise require the
standard `ExitOnError 1`, `Reset`, `Go`, `Exit` sequence, without file references.

Context and private snapshots do not establish which firmware is running on a
physical device. Flash builds before capturing; reset and RTT never configure or
build. After direct CMake reconfiguration, run the preparation script before an
NSX attach. Missing/stale contexts require preparation; malformed or wrong-identity
contexts fail even when an explicit serial is supplied. Offline RTT inspection does
not enumerate probes; execution revalidates and analyzes its own private ELF copy.
