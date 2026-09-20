---
title: SDK providers
description: How an NSX app gets its AmbiqSuite payload, which modules wrap it, and how to build against an SDK tree of your own.
---

Every NSX app builds on top of a vendor SDK. The module that supplies it is the app's SDK
provider, and it is the one module an app can have exactly one of.

## There is one provider

The provider is `nsx-ambiqsuite`, a module of type `sdk_provider` that carries an
AmbiqSuite payload under its `sdk/` directory. NSX's CMake accepts one value:

```text
Unsupported NSX_SDK_PROVIDER='zephyr' (expected 'ambiqsuite').
```

Modules declare which provider they need through
`constraints.required_sdk_provider`, and an app's closure is rejected if it ends up with
more than one provider module. That constraint exists so that the model has room for
another provider, not because there is a second one to pick from.

## You do not choose it, the board does

Provider selection is derived, not configured. Each packaged board's `board.yaml` declares
`sdk_provider: ambiqsuite`, and CMake infers the provider from the board being a
registered one. For a custom board, NSX follows the board's parent link before giving up:

```text
Unable to infer SDK provider for board 'my_board'. Set -DNSX_SDK_PROVIDER=ambiqsuite.
```

There is no `nsx.yml` key and no CLI flag for picking a provider. If you are seeing that
message, the fix is normally in the board definition rather than on the command line. See
[Adding a board](/neuralspotx/guides/contribute/adding-a-board/).

## What resolution produces

Once the provider is selected, configure sets four CMake variables that the rest of the
build reads:

| Variable | What it holds |
| --- | --- |
| `NSX_SDK_PROVIDER` | The selected provider, `ambiqsuite`. |
| `NSX_AMBIQSUITE_ROOT` | The directory the SDK payload was found in. |
| `NSX_AMBIQSUITE_VERSION` | The release channel the app tracks, not a numeric SDK version. |
| `NSX_SELECTED_SDK_TARGET` | The CMake target the wrappers link against. |

By default the root is the `sdk/` payload inside the vendored `nsx-ambiqsuite` module. If
neither that nor a fallback location exists, configure stops:

```text
SDK provider 'ambiqsuite' selected for board 'apollo510_evb', but the AmbiqSuite root
could not be located.
Set -DNSX_AMBIQSUITE_ROOT_OVERRIDE=... or vendor the nsx-ambiqsuite module so its sdk/
payload is present.
```

In an app that has been configured normally, that message means `modules/` is incomplete.
Run `nsx sync`.

## The wrapper modules

Apps rarely include AmbiqSuite headers directly. A small set of modules wraps the SDK and
presents the surfaces the rest of the graph depends on: `nsx-ambiq-hal` and `nsx-soc-hal`
for the hardware abstraction layer, `nsx-ambiq-bsp` for the board support package, and
`nsx-cmsis-startup` for the CMSIS startup and system pieces.

Depending on a wrapper rather than on the provider is what makes a module portable. The
wrapper is the thing whose interface NSX controls; the SDK underneath it is not.

## Which revision you are on

The SDK revision an app resolves to comes from NSX's registry, and it is not uniform: the
registry pins different SDK revisions for different SoC families, because a part is
supported from the first SDK release that ships it.

Do not read the revision off a documentation page. Read it from the app:

```bash
nsx module describe nsx-ambiqsuite
```

The [module catalog](/neuralspotx/modules/catalog/) carries the same data for every module
NSX pins, generated from the registry rather than written by hand.

:::note[Some SDK modules have no catalog page]
Several modules live inside the SDK monorepo rather than being registry entries of their
own. They resolve and build normally as part of an SoC family's baseline, but there is no
catalog page to link to and `nsx module add` will not find them by name.
:::

## Integration is from source

NSX vendors the SDK as source and compiles it as part of your build. There is no prebuilt
or binary integration mode: a module resolves from a git repository, from a tree packaged
inside the NSX wheel, from a local path or from your own vendored copy, and in every case
what lands in `modules/` is source that the build compiles.

That is why `modules/` is large, and it is also why a symbol you cannot explain is
traceable: the code is in the app.

## Building against your own SDK tree

`--sdk-root <path>` points the build at an AmbiqSuite tree somewhere else on your machine,
by way of the `NSX_AMBIQSUITE_ROOT_OVERRIDE` CMake cache variable. Use it to test an SDK
change before it is packaged as a module revision.

```bash
nsx build --sdk-root /opt/AmbiqSuite
```

It applies to `configure`, `build`, `flash` and `view`. Two things to know:

- The tree you point at is **not recorded in `nsx.lock`**, so the lock and the SBOM no
  longer describe the binary you produced. NSX warns when you use it.
- It **cannot be combined with `--frozen`**, because that flag's whole purpose is to
  guarantee the build matches the lock:

  ```text
  --sdk-root (/opt/AmbiqSuite) cannot be combined with --frozen: ... Drop one of the two flags.
  ```

An empty `--sdk-root` clears a previously cached override, which is how you get back to
the vendored payload without deleting the build tree.

:::caution[Not for release builds]
An override is a development escape hatch. Anything you intend to reproduce, ship or
account for in an SBOM should build from the vendored module that `nsx.lock` pins.
:::
