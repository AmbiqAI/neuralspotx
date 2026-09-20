---
title: The app model
description: What an NSX app is, why it vendors its own modules and boards, and the choices nsx create-app asks you to make.
---

An NSX app is a self-contained CMake project. It owns its source, its manifest, its
pinned dependency set and the vendored copy of every module it builds against. Nothing
about it depends on state elsewhere on your machine except the `nsx` CLI itself and your
compiler.

That is the whole model. The rest of this page is why it is built that way and what it
means for how you work.

## An app is the unit of work

There is no workspace, no global project registry and no shared build directory. You
create an app, you work in it, and you can delete it without leaving anything behind.

Two apps on the same machine can pin different revisions of the same module and neither
notices the other. An app you cloned from a colleague builds from its own `nsx.lock`
rather than from whatever your machine happens to have cached.

Commands that act on an app find it by walking up from your working directory until they
see an `nsx.yml`. That is why the examples throughout these guides just say `nsx build`
with no path. Use `--app-dir` when you want to act on an app somewhere else.

## Everything is vendored into the app

Module sources land in `modules/` inside the app. Board definitions land in `boards/`.
Neither is a reference to a shared location; they are real directories with real files
you can open, grep and step through in a debugger.

This costs disk space and buys three things:

- **The build is inspectable.** When a link fails, the source that failed to link is in a
  directory you can read, not behind a package manager.
- **The build is reproducible.** `nsx.lock` pins every module to a commit and a content
  hash. `nsx sync --frozen` will refuse to proceed if what is on disk no longer matches.
- **The app outlives NSX.** The generated tree is ordinary CMake and Ninja. If you want to
  graduate an app into your own build system, you already have all the sources.

`modules/` and `build/` are gitignored by the generated `.gitignore`, because `nsx.lock`
is enough to reconstruct them. Commit `nsx.yml` and `nsx.lock`; let NSX re-fetch the rest.

:::note[When you do want module sources in git]
Declaring a module as `vendored` in `nsx.yml` flips that default: the module's tree becomes
part of your repository and `nsx sync` stops touching it. See
[Lock and sync](/neuralspotx/guides/modules/lock-and-sync/).
:::

## Creating an app

[Create your first app](/neuralspotx/getting-started/first-app/) is the walkthrough. This
section is about the decisions that walkthrough makes for you.

### The board comes first

`--board` fixes the SoC, the startup and linker behavior, the flash and SWO settings and
the SDK provider for the app. It defaults to `apollo510_evb`. Everything else NSX resolves
follows from it, which is why there is no meaningful way to create an app without one.

`--soc` overrides the SoC that the board would otherwise imply. You need it only for a
board NSX cannot map to an SoC on its own, which it tells you about directly:

```text
Unable to infer --soc for board 'my_board'. Pass --soc explicitly.
```

See [Boards and targets](/neuralspotx/guides/apps/boards-and-targets/) for how target
selection works after the app exists, including building one app for several boards.

### The template decides what the first build does

| Template | What you get |
| --- | --- |
| `default` | A minimal app: initialize the runtime core, then print to SWO in a loop. |
| `npu-tflm` | TFLite Micro inference on the Ethos-U85 NPU. Seeds `nsx-helia-rt` and `nsx-npu`, and ships a Vela model harness plus a `tools/tflite_to_header.py` converter. |

`npu-tflm` declares `atomiq110` as its SoC, so it needs a board on that family. Anything
else is rejected with the list of templates NSX knows:

```text
Unknown app template 'tflite'. Known templates: default, npu-tflm
```

### Bootstrapping is optional

By default `create-app` clones the starter modules the board's profile calls for and
writes `boards/<board>/`. `--no-bootstrap` skips both: you get the app skeleton, an empty
`modules/`, no `boards/` directory, and `baseline: none` recorded in `nsx.yml`.

Use it when you have no network, or when you intend to choose the module set yourself
rather than start from the board's baseline.

### Writing into a directory that is not empty

`create-app` refuses by default:

```text
App directory already exists and is not empty: /home/you/my_app
```

`--force` allows it. It overwrites the generated files it owns; it does not clean the
directory first.

The remaining flags are on the
[`nsx create-app`](/neuralspotx/reference/cli/create-app/) reference page, which is
generated from the CLI itself.

## What the app owns and what NSX owns

| You own | NSX regenerates |
| --- | --- |
| `src/`, and any other source you add | `cmake/nsx/` |
| `CMakeLists.txt` | `boards/<board>/` |
| `nsx.yml` | `modules/` |
| `nsx.lock`, by running `nsx lock` | `build/<board>/` |

Editing anything in the right-hand column works until the next `nsx configure`, `nsx sync`
or `nsx lock` overwrites it. If you need to change how a module builds, change the module,
not the vendored copy. [Custom modules](/neuralspotx/guides/modules/custom-modules/)
covers how to point an app at a module you control.

`CMakeLists.txt` is the interesting exception. NSX writes it once and then leaves it alone,
so adding source files, compile options or your own targets is normal CMake work.

## Next

- [App layout](/neuralspotx/guides/apps/app-layout/) walks the generated directory in
  detail.
- [Using modules](/neuralspotx/guides/modules/using-modules/) covers changing what the app
  is made of.
