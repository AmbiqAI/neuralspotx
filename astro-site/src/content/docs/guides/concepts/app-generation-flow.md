---
title: App generation flow
description: What nsx create-app and nsx configure actually do, in order, and which files exist after each stage.
---

Two commands generate everything in an app. `nsx create-app` produces a project.
`nsx configure` produces a build. Knowing where the boundary sits tells you which command
to re-run when something is missing.

## What `nsx create-app` does

In order:

1. **Render the template tree.** The chosen template is written out: `CMakeLists.txt`,
   `src/main.c`, `README.md`, `.gitignore` and `cmake/presets/`.
2. **Copy the packaged CMake support** into `cmake/nsx/`. This is NSX's own build
   machinery, vendored so the app does not depend on the installed CLI to build.
3. **Write `nsx.yml`** with the board, the SoC, the toolchain, the channel and the starter
   profile.

If you passed `--no-bootstrap`, it stops here. You have a project that declares a target
and nothing else, with an empty `modules/` and no `boards/` directory.

Otherwise it continues:

4. **Acquire the seed modules.** The board's starter profile names the modules an app for
   that board begins with, and they are cloned into `modules/`.
5. **Resolve the dependency closure** from those seeds.
6. **Update `nsx.yml`** with what resolution determined.
7. **Write the generated module wiring** that tells CMake where each module is and which
   targets it exports.
8. **Acquire the transitive modules** that the closure added beyond the seeds.
9. **Write the gitignore entries** for the directories that are reconstructible.
10. **Save the manifest** in its final, lean form.

The order matters in one respect that shows up in practice: seeds are fetched before the
closure is resolved, because the manifests that describe the graph live inside the module
repositories. NSX cannot know what a module depends on until it has the module. That is
why resolution needs network access, and why a failure here names a module you did not
list.

## What `nsx configure` does

1. **Lock, if there is no lock.** Resolve the graph, per target board, and write
   `nsx.lock`.
2. **Sync.** Make `modules/` match the lock, fetching what is missing and restoring what
   has drifted.
3. **Run CMake** with the board's fragments, the selected toolchain file and the resolved
   module wiring, generating `build/<board>/`.

So a fresh app gets its full module set on the first `nsx configure`, not on
`create-app`. Bootstrap fetches the starter set; configure fetches the closure.

[Lock and sync](/neuralspotx/guides/modules/lock-and-sync/) covers steps 1 and 2 in
detail, including how to run them separately and how to make them read-only.

## What exists after each stage

| After | You have |
| --- | --- |
| `create-app --no-bootstrap` | `nsx.yml`, `CMakeLists.txt`, `src/`, `cmake/nsx/`, `cmake/presets/`, empty `modules/` |
| `create-app` | The above plus `boards/<board>/` and the starter modules |
| `configure` | The above plus `nsx.lock`, the full `modules/` closure, `build/<board>/` and `.nsx/` |
| `build` | The above plus the linked image, `.bin` and `.map` under `build/<board>/` |

## Why generate at all

The alternative would be a build system that reads `nsx.yml` at compile time and decides
things dynamically. NSX writes the decisions down instead, which buys three things:

- **The output is inspectable.** `build/<board>/build.ninja` contains the real command
  lines. NSX itself reads that file to find the SEGGER flash and view invocations, which
  is a decent signal of how literally the generated tree is treated.
- **The output is portable.** An app can be built by CMake and Ninja without NSX present,
  which is what makes graduating a prototype into another build system tractable.
- **Failures land early.** Compatibility and closure problems surface at lock time with a
  module name, rather than at link time with an unresolved symbol.

The cost is that generated files go stale. Re-running `nsx configure` is the answer to
almost every "it worked yesterday" in a generated tree, and `nsx clean --full` is the
answer to the rest.
