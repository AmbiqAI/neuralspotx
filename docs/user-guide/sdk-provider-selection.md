# SDK Provider Selection

NSX separates raw SDK provider repos from the higher-level wrapper modules that
apps actually consume.

## Provider

There is a single AmbiqSuite provider covering all supported SoCs:

- `nsx-ambiqsuite`

## What the App Sees

Apps do not usually choose an SDK provider directly.

Instead:

1. the selected board implies a SoC family
2. the board’s starter profile selects the provider and SoC module set
3. the profile can pin a specific provider revision or branch
4. the chosen revision is recorded in `nsx.yml`

## Why This Matters

This keeps board defaults explicit without forcing users to manually manage SDK
lineage for normal app creation.

## Out-of-tree SDK (`--sdk-root`)

`nsx configure`, `nsx build`, `nsx flash`, and `nsx view` accept
`--sdk-root PATH` (`AppActionRequest.sdk_root` in the Python API). It is an
**escape hatch**: CMake receives `-DNSX_AMBIQSUITE_ROOT_OVERRIDE=PATH` and
builds against that AmbiqSuite checkout instead of the vendored
`nsx-ambiqsuite` module.

Use it for SDK bring-up or bisecting a vendor drop, and be aware of what it
gives up:

- `nsx.lock`, the SBOM, and `--frozen` describe the *vendored* SDK only. A
  binary built with `--sdk-root` is not reproducible from the app's lock, and
  NSX prints a warning saying so on every run.
- `--sdk-root` combined with `--frozen` is refused: a frozen build cannot be
  verified against an SDK the lock does not record.
- The path must be an existing directory; anything else fails before any
  module sync.
- The override is a CMake cache entry. NSX always emits it (empty when the flag
  is omitted), so a later `nsx configure` without `--sdk-root` returns the
  build tree to the vendored module. `nsx build` / `flash` / `view` with an
  explicit `--sdk-root` that differs from the cached value reconfigure first;
  without the flag they keep whatever the tree was last configured with.

## Wrapper Modules

Apps typically consume:

- `nsx-ambiq-hal`
- `nsx-ambiq-bsp`
- `nsx-soc-hal`
- `nsx-cmsis-startup`

These wrappers build on top of the raw SDK provider.
