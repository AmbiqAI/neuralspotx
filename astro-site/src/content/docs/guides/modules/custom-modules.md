---
title: Custom modules
description: Scaffold a module of your own, wire its CMake surface, validate its manifest, and point an app at it from a path, a fork or your own repository.
---

A custom module is an ordinary NSX module that NSX's registry does not pin. It has the
same manifest, the same CMake contract and the same resolution behavior as a packaged one.
The only difference is that you say where it comes from.

Write one when you have firmware you want to reuse across apps or share with a colleague.
For a change you only need in one app, plain CMake in that app's `CMakeLists.txt` is less
work.

## Scaffold it

```bash
nsx module init my-sensor --type algorithm --summary "Accelerometer feature extraction"
```

That writes a module directory with a manifest, CMake, a header and a source stub, ready
to build. The flags seed the manifest: `--type` picks the module class, `--dependency`,
`--board`, `--soc` and `--toolchain` are each repeatable and declare what the module needs
and what it claims to work with. Compatibility defaults to `*` for boards and SoCs and to
`arm-none-eabi-gcc` for toolchains, so tighten those to what you have actually built.

The eight module types are `algorithm`, `backend_specific`, `board`, `portable_api`,
`runtime`, `sdk_provider`, `soc` and `tooling`. [The module
model](/neuralspotx/guides/concepts/module-model/) explains what each one means and which
rules NSX enforces per type.

## The manifest

`nsx-module.yaml` is the contract. Every field, required and optional, is on the generated
[`nsx-module.yaml` reference](/neuralspotx/reference/config/nsx-module-yaml/), so this page
only covers the parts that catch people out.

- **`build.cmake.package` and `build.cmake.targets`** are how the rest of the build reaches
  your code. The package name is the module name with hyphens turned into underscores:
  `my-sensor` becomes `my_sensor`. The conventional target is the package name under the
  `nsx::` namespace, with an `nsx_` prefix dropped if present: `my-sensor` gives
  `nsx::my_sensor`, `nsx-timer` gives `nsx::timer`. `nsx module init` writes both for you.
- **`depends.required` is resolved; `depends.optional` is not.** Optional dependencies are
  searchable metadata that tell a reader what your module can work with. Nothing installs
  them.
- **`compatibility` is enforced.** NSX rejects an app that pairs your module with a board,
  SoC or toolchain the manifest does not list. Declaring `*` everywhere makes the check
  useless and makes the catalog page misleading.
- **The semantic fields are how anyone finds you.** `summary`, `capabilities`,
  `use_cases`, `anti_use_cases`, `agent_keywords`, `example_refs` and `composition_hints`
  are optional, and they are what `nsx module search` matches against and what the catalog
  page renders. `anti_use_cases` is worth writing: saying what a module is wrong for saves
  more time than another sentence about what it is right for.

Check your work before an app ever sees it:

```bash
nsx module validate ./my-sensor
nsx module validate ./my-sensor --json
```

## The CMake surface

Your module declares a package and one or more targets; NSX generates the wiring that
makes them findable and links them into the app. Keep the target's public include
directories and link dependencies honest, because that is the only description the app has
of how to consume you.

Dependencies belong in both places. The manifest tells NSX what to resolve and vendor; the
CMake `target_link_libraries` tells the compiler and linker what to use. Declaring a
dependency in only one of the two produces either a missing source tree or a missing
symbol, depending on which half you forgot.

## Pointing an app at it

Three ways, by how much you want NSX to manage.

### A path you are actively editing

```bash
nsx module add my-sensor --local --path ../my-sensor
```

`nsx.yml` records a `source.path`. Every `nsx sync` mirrors that directory into
`modules/my-sensor/`, so your edits show up in the next build. `nsx.lock` records a content
hash of the source directory, which means `--frozen` will notice when it changes. This is
the mode for developing a module and an app together.

### Sources you want in your repository

```bash
nsx module add my-sensor --vendored
```

`modules/my-sensor/` becomes yours: committed to your repository, never re-fetched, never
overwritten by `nsx sync`. The lock records only a content hash so drift is still
detectable. Use this when the app must build with no network and no second repository.

### A repository, or a fork of a packaged module

```bash
nsx module register my-sensor \
  --metadata ../my-sensor/nsx-module.yaml \
  --project my-sensor \
  --project-url https://github.com/you/my-sensor.git \
  --project-revision v0.1.0
```

This writes an app-local registry entry under `module_registry` in `nsx.yml` and vendors
the module in. From then on it resolves like any registry module: pinned to a revision,
re-fetched by `nsx sync`, reported by `nsx outdated`.

The same command with `--override` replaces where a module NSX already pins comes from,
which is how you test a fork of a packaged module without changing NSX. App-local entries
take precedence over the packaged registry, and the override lives in your app's manifest,
so anyone cloning the app gets the fork too. `--project-local-path` vendors from a
filesystem path instead of a git URL, and `--dry-run` shows the manifest change without
writing it.

:::caution[An override is invisible in the catalog]
The [module catalog](/neuralspotx/modules/catalog/) shows what NSX pins, not what your app
overrides. Once you override a module, `nsx module describe <name>` run inside the app is
the accurate source, not the catalog page.
:::

## Rules NSX enforces

- No dependency cycles. `Dependency cycle detected at module '<name>'` is a manifest
  problem, not an app problem.
- At most one `sdk_provider` module in an app. See
  [SDK providers](/neuralspotx/guides/modules/sdk-providers/).
- A board module depends on exactly one SoC module.
- Compatibility is checked at resolution time, so a mismatch fails `nsx lock`, not the
  compiler.

## Publishing it more widely

Getting a module into the packaged registry, so that other people's apps can add it by
name, is a change to NSX itself. See
[Adding a module](/neuralspotx/guides/contribute/adding-a-module/).
