# SDK Providers

Raw SDK provider repos expose the imported SDK payload used by NSX.

Current families:

- `nsx-ambiqsuite-r3`
- `nsx-ambiqsuite-r4`
- `nsx-ambiqsuite-r5`

## Current Branch Model

- `nsx-ambiqsuite-r3`: `main`, `r3.1.1`
- `nsx-ambiqsuite-r4`: `main`, `r4.4.1`, `r4.5.0`
- `nsx-ambiqsuite-r5`: `main`, `r5.1`, `r5.2`, `r5.2-alpha`, `r5.3`

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
