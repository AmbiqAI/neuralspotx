# SDK Providers

Each AmbiqSuite release line is delivered as a single consolidated SDK monorepo
that vendors the imported SDK payload, the HAL/BSP wrappers, and the shared NSX
module set used by NSX.

Current families:

- `nsx-ambiq-sdk-r3` (provider module `nsx-ambiqsuite-r3`)
- `nsx-ambiq-sdk-r4` (provider module `nsx-ambiqsuite-r4`)
- `nsx-ambiq-sdk-r5` (provider module `nsx-ambiqsuite-r5`)

## Current Branch Model

- `nsx-ambiq-sdk-r3`: `main`
- `nsx-ambiq-sdk-r4`: `main`
- `nsx-ambiq-sdk-r5`: `main`

## Contributor Expectations

When updating SDK providers:

1. keep each branch tied to a coherent vendor drop
2. do not mix multiple upstream drops in one branch
3. update board defaults only after validating the branch for that target
4. keep wrapper modules compatible with the chosen provider structure

## Related Updates

Provider changes usually require updates in:

- starter profiles
- board defaults
- provider metadata
- user-facing docs when supported targets change
