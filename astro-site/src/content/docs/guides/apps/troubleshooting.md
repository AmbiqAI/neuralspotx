---
title: Troubleshooting
description: The errors NSX actually prints, what each one means, and the fix, from app discovery through module resolution to flashing and SWO.
---

This page is organized around the messages NSX prints. If you have one in front of you,
search this page for a distinctive fragment of it. Paths and names in the examples below
stand in for whatever yours says.

Before anything else, run [`nsx doctor`](/neuralspotx/getting-started/doctor/). A missing
compiler or a J-Link pack that is not on `PATH` produces failures much further downstream
than you would expect.

## NSX cannot find your app

```text
NSX app config not found: /home/you/nsx.yml
Run `nsx create-app <app-dir>` to create a new app.
```

`configure`, `build`, `flash`, `view` and `clean` locate the app by walking up from the
working directory looking for `nsx.yml`. This message means the walk reached the top
without finding one. Either `cd` into the app, pass `--app-dir <path>`, or pass the app as
the positional argument, which also resolves names under `./examples` in a source
checkout.

```text
Unable to determine target board from args or nsx.yml
```

The app's manifest declares no target and you did not pass `--board`. Add a `target.board`
or a `targets.default` to `nsx.yml`, or name a board on the command line. See
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/).

## Creating an app fails

```text
App directory already exists and is not empty: /home/you/my_app
```

Pick a different directory, or pass `--force` to write into this one. `--force` overwrites
the files NSX generates; it does not empty the directory first.

```text
Unknown app template 'tflite'. Known templates: default, npu-tflm
```

The message lists what is available. See
[The app model](/neuralspotx/guides/apps/app-model/).

```text
Unable to infer --soc for board 'my_board'. Pass --soc explicitly.
```

The board is not one NSX can map to an SoC on its own, which normally means it is a board
you are adding rather than a packaged one. Pass `--soc`, and see
[Adding a board](/neuralspotx/guides/contribute/adding-a-board/).

## Module resolution fails

```text
Unable to resolve dependency metadata for nsx.yml modules [nsx-audio]: ...
Run `nsx lock` with the required module sources available so nsx.lock can record the
full dependency closure.
```

NSX could not read a module's manifest. In practice that is a network failure, a private
repository you are not authenticated against, or a revision that no longer exists
upstream. Resolution needs to reach every module's source, because the manifests that
describe the graph live in the module repositories rather than in NSX.

```text
Dependency cycle detected at module 'nsx-foo'
```

Two modules require each other, directly or through a chain. This is a problem in the
manifests, not in your app. If the modules are yours, break the cycle by moving the shared
piece into a third module; see
[Custom modules](/neuralspotx/guides/modules/custom-modules/).

```text
Module 'nsx-uart' is already a direct dependency in nsx.yml
```

It is already listed. `nsx module list` shows what the app depends on directly. Note that
a module can be present in the resolved graph as a transitive dependency without being a
direct one, which is the usual reason this is surprising.

```text
--board apollo4p_evb not in the app's supported targets (apollo510_evb)
```

`nsx module add --board` can only scope a dependency to a board the app already declares.
Add the board to `targets.supported` first.

## Drift and `--frozen`

`--frozen` turns any disagreement between `nsx.yml`, `nsx.lock` and `modules/` into an
error instead of quietly correcting it. It is the right flag for CI and the wrong flag for
day-to-day work, because the corrections it refuses to make are usually the ones you want.

```text
Vendored module 'my-module' content drifted from lock ...
Local module 'my-module' content drifted from lock ...
Local source for 'my-module' at /home/you/src/my-module has drifted ...
```

Something on disk no longer matches the content hash recorded in `nsx.lock`. If you
changed the module on purpose, re-run `nsx lock` to record the new state. If you did not,
`nsx sync` without `--frozen` restores it.

```text
/home/you/my_app/nsx.lock not found. Run `nsx lock` first (or drop --frozen).
```

There is no lock to verify against. Without `--frozen`, `nsx configure` would have written
one.

```text
--sdk-root (/opt/AmbiqSuite) cannot be combined with --frozen: ... Drop one of the two flags.
```

An SDK tree pointed at by `--sdk-root` is not recorded in `nsx.lock`, so the build cannot
be reproduced from the lock. NSX refuses the combination rather than producing a binary it
cannot account for. See [SDK providers](/neuralspotx/guides/modules/sdk-providers/).

```text
--sdk-root is not a directory: /opt/AmbiqSuit
```

A typo in the path, usually.

## Building fails

```text
Missing build.ninja in build directory: /home/you/my_app/build/apollo510_evb
```

The build tree was never generated or has been partly deleted. Run `nsx configure`, or
`nsx clean --full` followed by `nsx build`, which configures from scratch.

A compiler error inside a vendored module is a real compiler error: the sources under
`modules/` are the sources being compiled, and the path in the error message is the file
to open. If you edited a vendored module to get past it, remember that `nsx sync` will
restore the original.

```text
/home/you/my_app/nsx.lock not found. Run `nsx lock` first.
```

`nsx sbom` and the lock-reading commands need a resolved graph. `nsx configure` writes one
as a side effect; `nsx lock` writes one on its own.

## Flashing fails

```text
No J-Link probes found.
```

`nsx probes` found nothing attached. Check the cable and that the J-Link pack is installed,
then re-run `nsx doctor`, which checks for the SEGGER runtime specifically.

```text
J-Link exited successfully for target 'my_app_flash' but printed no recognized flash
result: neither a 'Flash download: Total' summary nor a 'Skipped. Contents already match'
notice. The device was most likely programmed; this usually means the installed J-Link
Commander words its summary differently. Inspect the echoed J-Link output for what
actually happened.
```

NSX reads J-Link's own output to decide whether programming happened, and different J-Link
Commander releases word the summary differently. The message says what to do: read the
echoed J-Link output above it. This is a reporting limitation, not a failed flash.

With more than one probe attached, pass `--probe-serial` to say which one. That always
forces a reconfigure, because the serial is baked into the generated SEGGER command files.

## SWO shows nothing

The most common cause is not an error at all. On `apollo3p`, `apollo4l`, `apollo4p` and
`apollo510b`, `nsx view` attaches without resetting the target, so if the firmware already
ran past its output you see an idle stream. NSX says so when it happens:

```text
Using attach-only SWO view for this secure-reset SoC; flash first or pass --reset-on-open to force a reset.
```

Flash first, or pass `--reset-on-open`. On other SoCs `view` resets by default, and
`--reset-delay-ms` controls how long it waits before reading.

If the firmware never enabled SWO output, nothing will appear regardless. The generated
app calls `nsx_itm_printf_enable()` before its first `nsx_printf()`; see
[System initialization](/neuralspotx/guides/system/system-init/).

```text
Unable to resolve the SEGGER SWO viewer command for target 'my_app_view' from /home/you/my_app/build/apollo510_evb/build.ninja
```

NSX reads the viewer invocation out of the generated Ninja file and could not find it.
That means the build tree is stale or was generated by a different NSX version. Re-run
`nsx configure`.

```text
Cannot open capture file /var/log/swo.txt: Permission denied
```

`--capture` could not open the path for writing. The underlying reason is quoted after the
colon.

## Still stuck

- `nsx -v` repeats to increase verbosity, which shows the subprocesses NSX runs.
- The generated tree is ordinary CMake and Ninja, so `ninja -C build/<board> -v` shows the
  exact compiler command lines.
- `nsx doctor --json` and `nsx commands --json` give machine-readable state if you are
  scripting around a failure. See the
  [Python API guide](/neuralspotx/guides/python-api/).
