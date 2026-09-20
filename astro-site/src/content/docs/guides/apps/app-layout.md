---
title: App layout
description: Every file and directory in a generated NSX app, when each one appears, and which ones you edit.
---

A generated app grows in three steps. `nsx create-app` writes the skeleton, bootstrap adds
the vendored dependencies, and `nsx configure` adds the build tree. Knowing which step
produced a given directory tells you whether you may edit it.

## After `nsx create-app`

```text
my_app/
├── .gitignore
├── CMakeLists.txt
├── README.md
├── boards/
│   └── apollo510_evb/
├── cmake/
│   ├── nsx/
│   └── presets/
├── modules/
├── nsx.yml
└── src/
    └── main.c
```

| Path | What it is | Edit it? |
| --- | --- | --- |
| `nsx.yml` | The app manifest: board and SoC target, toolchain, release channel, starter profile, and the list of modules you depend on directly. | Yes. This is the file you change. |
| `CMakeLists.txt` | An ordinary top-level CMake file. Declares `cmake_minimum_required(VERSION 3.24)`, includes the packaged NSX support and links your executable. | Yes. NSX writes it once and does not rewrite it. |
| `src/main.c` | The generated application. `npu-tflm` writes `src/main.cc` instead. | Yes. |
| `.gitignore` | Excludes `modules/`, `build/` and `.nsx/`, which are all reconstructible from `nsx.lock`. | Yes, but keep those three entries. |
| `README.md` | A short readme for the app, including its build and flash sequence. | Yes. |
| `cmake/nsx/` | Packaged CMake support: module wiring, the toolchain files, the SEGGER flash and reset templates. | No. Overwritten on every `create-app` and refreshed as NSX updates. |
| `cmake/presets/` | `CMakePresets.json`, so an IDE can open the project directly. Defines `gcc-ninja`, `armclang-ninja` and `atfe-ninja`. | No. |
| `boards/<board>/` | The vendored board module: `board.yaml` plus the board, BSP, SoC, memory and debug CMake fragments. | No. Re-vendored by `nsx sync`. |
| `modules/` | Where vendored module sources land. | No. See below. |

:::caution[`boards/` only exists after bootstrap]
A default `nsx create-app` writes `boards/<board>/` and populates `modules/`. Running it
with `--no-bootstrap` writes neither: you get an empty `modules/`, no `boards/` directory
at all, and `baseline: none` in `nsx.yml`. Both appear the first time you run `nsx lock`
and `nsx sync`, or `nsx configure`, with the modules you want declared.
:::

### Inside `modules/`

One directory per module in the resolved graph, each one a real source tree at the commit
`nsx.lock` pins. After a default bootstrap on an Apollo510 EVB that is `nsx-ambiq-sdk` and
`nsx-pmu-armv8m`; after a `nsx configure` it is the full closure, which is larger.

Do not edit a vendored module in place. `nsx sync` compares each directory against the
content hash in `nsx.lock` and restores anything that has drifted. If you need to change a
module, [point the app at your own copy](/neuralspotx/guides/modules/custom-modules/)
instead.

The one exception is a module declared `vendored` in `nsx.yml`. Those are yours: they are
committed to your repository and `nsx sync` leaves them alone.

## After `nsx configure`

```text
my_app/
├── .nsx/
├── build/
│   └── apollo510_evb/
├── nsx.lock
└── ...
```

| Path | What it is | Commit it? |
| --- | --- | --- |
| `nsx.lock` | The resolved dependency graph: every module pinned to a project, a revision, a commit and a content hash, recorded per target board. | Yes. It is what makes the build reproducible. |
| `build/<board>/` | The generated CMake and Ninja tree, one directory per board. Holds the linked image, the `.bin`, the `.map` and a generated `jlink/` directory of SEGGER command files. | No. |
| `.nsx/` | NSX's own bookkeeping, including the sync lock file. | No. |

Each board you build for gets its own `build/<board>/`, so switching targets does not
invalidate the previous one. See
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/).

## What to commit

Commit `nsx.yml`, `nsx.lock`, `CMakeLists.txt`, `src/` and `README.md`. That is enough for
anyone with the same NSX version to reproduce your build exactly, because `nsx.lock`
records commits and content hashes rather than version ranges.

Leave `modules/`, `boards/`, `build/` and `.nsx/` out, which is what the generated
`.gitignore` already does. `boards/` is re-vendored from the packaged board definition and
`modules/` from the lock, so neither carries information the lock does not already have.

:::tip[Checking a clone builds the same thing]
`nsx sync --frozen` fails rather than correcting when `modules/` does not match `nsx.lock`,
and `nsx lock --check` reports manifest drift without writing. Together they are the CI
check that a tree has not quietly moved. See
[Lock and sync](/neuralspotx/guides/modules/lock-and-sync/).
:::
