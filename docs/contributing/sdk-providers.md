# SDK Providers

All AmbiqSuite SoCs are delivered from a single consolidated SDK monorepo that
vendors the imported SDK payload, the HAL/BSP wrappers, and the shared NSX
module set used by NSX.

Current bundle:

- `nsx-ambiq-sdk` (provider module `nsx-ambiqsuite`, wrappers `nsx-ambiq-hal` / `nsx-ambiq-bsp`)

All provider and wrapper modules currently resolve to this one project on
`main`. This is a temporary stable-registry policy exception, not the desired
release end state. See
[SDK Upstream Model](../architecture/sdk-upstream-plan.md) for the full picture.

## Current Revision Model

- `nsx-ambiq-sdk`: `main`

Stable registry revisions are expected to use immutable version tags or full
commit SHAs. The policy validator allowlists exactly `nsx-ambiq-sdk@main` (and
the packaged `neuralspotx@main` self-reference) until their immutable pins are
available. Do not add another floating ref to bypass that gate; use an explicit
app/workspace development override instead.

## Contributor Expectations

When updating the SDK provider:

1. keep each `nsx-ambiq-sdk` update tied to a coherent vendor drop
2. do not mix multiple upstream drops in one update
3. update board defaults only after validating the new drop for that target
4. keep wrapper modules compatible with the provider structure

## Related Updates

Provider changes usually require updates in:

- starter profiles
- board defaults
- provider metadata
- user-facing docs when supported targets change
