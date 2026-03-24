# SDK Upstream Plan

This document defines the intended upstream shape for the raw SDK provider
repos.

## Goal

Each raw SDK provider repo should have a coherent provenance story that can be
explained clearly from the repo itself.

The preferred model is:

1. one repo per major provider family
2. one branch per upstream minor or variant lineage when needed
3. NSX board defaults select the appropriate provider revision

## R3

Local inventory:

1. `R3.1.1`

Local board/header coverage in `R3.1.1` already includes:

1. `apollo3_evb`
2. `apollo3_evb_cygnus`
3. `apollo3p_evb`
4. `apollo3p_evb_cygnus`

Recommendation:

1. upstream `nsx-ambiqsuite-r3` as a single repo
2. make `r3.1.1` the default branch or a first-class release branch
3. no additional R3 branch split is required based on current local coverage

## R4

Local inventory:

1. `R4.4.1`
2. `R4.5.0`

Both local drops expose the same board/header family needed for current NSX
coverage:

1. `apollo4l_evb`
2. `apollo4l_blue_evb`
3. `apollo4p_evb`
4. `apollo4p_blue_kbr_evb`
5. `apollo4p_blue_kxr_evb`

Recommendation:

1. upstream `nsx-ambiqsuite-r4` as a single repo
2. default to `r4.5.0`
3. keep an optional `r4.4.1` branch only if a real board or binary-compat
   requirement emerges

Current evidence does not justify making board defaults depend on `r4.4.1`
instead of `r4.5.0`.

## R5

Local inventory:

1. `R5.1.0_rc27`
2. `R5.2.0`
3. `R5.2.alpha.1.1`
4. `R5.3.0`

Current board support maps most cleanly to these revisions:

1. `apollo510_evb` -> `r5.3`
2. `apollo5b_evb` -> `r5.2`
3. `apollo510b_evb` -> `r5.1`
4. `apollo330mP_evb` -> `r5.2-alpha`

Recommendation:

1. upstream `nsx-ambiqsuite-r5` as one repo
2. create real branches:
   - `r5.1`
   - `r5.2`
   - `r5.2-alpha`
   - `r5.3`
3. stop treating the current locally normalized tree as the long-term upstream
   default
4. keep NSX board profiles responsible for selecting the correct branch

## Apollo510L

`apollo510L_eb` should remain blocked for now.

Local history currently provides:

1. headers
2. MCU directory
3. system source

But it does not yet provide a clean board/BSP/lib bundle in the current SDK
history. Until that exists as a coherent upstream branchable payload, NSX
should not expose `apollo510L_eb` as a built-in board.
