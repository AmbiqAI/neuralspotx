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

## Wrapper Modules

Apps typically consume:

- `nsx-ambiq-hal`
- `nsx-ambiq-bsp`
- `nsx-soc-hal`
- `nsx-cmsis-startup`

These wrappers build on top of the raw SDK provider.
