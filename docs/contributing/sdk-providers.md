# SDK Providers

All AmbiqSuite SoCs are delivered from a single consolidated SDK monorepo that
vendors the imported SDK payload, the HAL/BSP wrappers, and the shared NSX
module set used by NSX.

Current bundle:

- `nsx-ambiq-sdk` (provider module `nsx-ambiqsuite`, wrappers `nsx-ambiq-hal` / `nsx-ambiq-bsp`)

All provider and wrapper modules resolve to the immutable `v5.2.24` release of
this project. See
[SDK Upstream Model](../architecture/sdk-upstream-plan.md) for the full picture.
The release is a provenance correction: its binary payload is unchanged from
`v5.2.23`, while 22 stale ACfE manifest hashes and their ABI provenance are
corrected in the SDK release.

## Current Revision Model

- `nsx-ambiq-sdk`: `v5.2.24`
- `nsx-pmu-armv8m`: `v0.2.0`

Stable registry revisions must use immutable version tags or full commit SHAs.
The packaged `neuralspotx@main` self-reference is the sole *permanent*
floating-ref allowance (`registry_policy.PERMANENT_FLOATING_REF_KEYS`). Any
other floating stable ref must be a temporary branch pin registered in
`TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST` with an `expires_on` date; past that
date `test_temporary_allowances_have_not_expired` fails until the pin is
collapsed to a tag/SHA and the allowance removed. Prefer an explicit
app/workspace development override over a temporary pin whenever possible.

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
