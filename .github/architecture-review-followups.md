# Architecture Review Follow-ups

Tracking checklist seeded from the 2026-06 codebase architecture/design review.
Items are in **execution order** — work top to bottom, one at a time, each in its
own commit on this branch. Check the box here and in the PR description as each
lands. Original review IDs (B/L/R) are kept in parentheses for traceability.

Ordering rationale: remove the import-time footgun first, then settle the board
descriptor as the single source of truth (CPU facts → redundant fields → magic
numbers → generated-fragment drift guard → inventory checks), then board-name
hardening and the provider decision, then the layering refactors in ascending
risk, and finally low-risk cleanup/docs.

Legend: **Sev** = severity (High / Med / Low), **Risk** = change risk.

## Foundation

- [x] **1 (R1) — Defer constants' import-time validation.** `constants.py` runs
  `load_board_descriptors()` and can `raise RuntimeError` at import, making the
  whole package (incl. `nsx doctor`) unimportable on a malformed descriptor.
  Move validation behind a callable so doctor can report gracefully. Do this
  first so later descriptor edits can't brick the package mid-series.
  _Sev: High · Risk: Low._
  - Done: `constants.validate_board_registry()` now centralizes the checks
    (descriptor load + both `_BOARD_ORDER` drift directions); import captures a
    `BoardDescriptorError` instead of raising, and the derived tables build
    defensively. `nsx doctor` surfaces problems via a new "Board registry" check.

## Board descriptor as single source of truth

- [x] **2 (B2) — Reconcile CPU facts to one owner.** `board.yaml.cpu`
  (core/float_abi/abi) duplicates the SDK's `facts/<skew>.cmake`
  (`NSX_CPU`/`NSX_FLOAT_ABI`/`NSX_ABI_FLAGS`), which calls itself the "single
  source of truth." Drop `cpu` from `board.yaml` and read from SoC facts, or add
  a cross-repo contract test. Remove the stale "mirrors board.cmake" docstring on
  `BoardCpu`. _Sev: High · Risk: Low._
  - Done: `cpu` is consumed only by `nsx board info` display, so it stays as the
    descriptor-facing copy; added skip-if-absent cross-repo contract test
    `tests/test_board_cpu_facts_contract.py` guarding it against the SDK SoC
    facts, and corrected the `BoardCpu` docstring to name the real source.
- [x] **3 (B3) — Audit `soc_family`.** It equals `soc` for all 15 boards today, so
  it carries no discriminating information. Either collapse it or make it mirror
  the SDK's `NSX_SOC_SERIES` grouping (e.g. apollo3 series grouping
  apollo3+apollo3p). _Sev: Low · Risk: Low._
  - Done (Option A): removed the redundant `soc_family` field from the
    `BoardDescriptor` dataclass, its parse/merge paths, the `board show`
    human/JSON output, and all 15 packaged `board.yaml` files. `metadata`'s
    starter-profile derivation now joins the registry `soc_families` table on
    the descriptor's `soc` (the keys already equalled `soc`), a zero-behavior
    change. Stale `NSX_SOC_FAMILY` note dropped from the board.yaml headers.
    The future idea of regrouping into an `NSX_SOC_SERIES`-style coarse bucket
    (e.g. folding apollo330 into apollo5) is deferred — no consumer needs it today.
- [x] **4 (B7) — Move board magic numbers into descriptors.** `AM_PACKAGE_BGA`
  and `STACK_SIZE=4096` are hardcoded inline in each `board.cmake` with no
  provenance. Promote to `board.yaml` (or SoC facts) with a comment.
  - Done (Option A): the two defines are identical across all 15 boards (global
    build defaults, not per-board facts), so rather than duplicate them into 15
    descriptors we documented their provenance in place — added inline comments
    in every `board.cmake` explaining `AM_PACKAGE_BGA` (AmbiqSuite chip-package
    selector, BGA variant) and `STACK_SIZE` (startup C-runtime stack bytes). No
    behavior change. Promoting to descriptor fields was deemed unnecessary while
    the values stay uniform; revisit if a board needs a different package/stack.
  _Sev: Low · Risk: Low._
- [x] **5 (B1) — Collapse board/SoC identity duplication.** The SoC string + part
  macros are restated across `board.yaml`, `soc.cmake`, `board.cmake`,
  `memory.cmake`, and `bsp.cmake` for every board, and each `board.yaml` carries
  a "Keep in sync with board.cmake" note. Make `board.yaml` the single
  declarative source and generate the CMake fragments from it, or — as a first
  step — add a drift test asserting `board.yaml.soc` matches the
  `nsx_load_soc_facts("…")` argument and that the SDK SoC-facts file exists.
  _Sev: High · Risk: Med (start with the test)._
  - Done (first step): added `tests/test_board_soc_identity_drift.py` asserting,
    for every board, that `board.yaml`'s `soc` equals the `soc.cmake`
    `nsx_load_soc_facts("…")` argument. The companion "SDK facts file exists"
    check is already covered by `tests/test_board_cpu_facts_contract.py` (B2).
    Deliberately did **not** assert `bsp.cmake`'s `NSX_AMBIQ_PART_NAME`: that is
    a board/BSP-owned fact that can legitimately differ from the SoC (e.g.
    `apollo510b_evb` loads `apollo510b` SoC facts but uses the `apollo510`
    MCU/BSP dir) — keeping the SoC and BSP layers distinct per design.
    The fuller "thread a single `NSX_SOC` / generate fragments from
    `board.yaml`" refactor is deferred, and the custom-board role-override path
    (custom boards supplying their own BSP/role modules instead of wholesale
    delegating to the parent EVB) is tracked separately as #154b.
- [ ] **6 (B6) — Validate SoC inventory symmetry.** `atomiq110` SoC facts exist
  with no NSX board; naming diverges (`apollo510L` vs `apollo510dL_evb`). Add a
  fast Python-level check that every board's `soc` resolves to an existing SDK
  facts file instead of failing late at CMake configure. _Sev: Med · Risk: Low._

## Board-name & provider hardening

- [ ] **7 (B4) — Harden mixed-case load-bearing identifiers.** `apollo510dL_evb`
  → `apollo510L`, `apollo330mP_evb` → `apollo330P`. Case quirks thread through
  dirs, CMake target names, and package names while only input boundaries are
  lowercased. Normalize internal string-equality or document the invariant.
  _Sev: Med · Risk: Med._
- [ ] **8 (B5) — Decide on the single-valued SDK-provider abstraction.**
  `SDKProvider` has one member; `nsx_board_table.cmake` is a 15-branch dispatch
  that always returns `"ambiqsuite"`; module gate requires
  `support.ambiqsuite=true`. Either simplify to a single helper (delete per-board
  branches) or document the intended multi-vendor contract. Replace the regex
  parse of `board.cmake` text in `nsx_sdk_providers.cmake` with a parent field
  read from `board.yaml`. _Sev: Med · Risk: Med._

## Layering refactors (ascending risk)

- [ ] **9 (L5) — Make the hardcoded default board configurable.**
  `board="apollo510_evb"` in `api/_app.py` (~L30) and
  `operations/_app_lifecycle.py` (~L80). _Sev: Low · Risk: Low._
- [ ] **10 (L4) — Fold `init_module_impl`'s 11 args into a request dataclass**
  (`operations/_app_lifecycle.py` ~L225); the codebase already uses request
  dataclasses elsewhere. _Sev: Low · Risk: Low._
- [ ] **11 (L6) — Replace ad-hoc dicts with dataclasses** where AGENTS.md asks for
  typed models: registry metadata `dict[str, Any]`
  (`module_registry/_metadata.py` ~L141) with nested `["support"]["ambiqsuite"]`
  indexing; `AppConfig.raw` (`models/_project.py` ~L365). _Sev: Med · Risk: Med._
- [ ] **12 (L1) — Move `board create` out of the CLI.** Logic lives in
  `cli/_cmd_board.py` (~L80) instead of `operations/`/`api/`; it's the one
  command that bypasses the stack. Push it down so the API can offer programmatic
  board creation. _Sev: Med · Risk: Med._
- [ ] **13 (L2) — Separate dependency computation from acquisition.**
  `_resolve_module_closure` triggers side-effectful `_acquire_modules_for_app`
  mid-DFS (`module_registry/_closure.py` ~L98). Split for testability and
  dry-run correctness. _Sev: Med · Risk: Med._
- [ ] **14 (L3) — Decompose the `_sync_app_impl_unlocked` god function**
  (`operations/_sync.py` ~L125, 200+ lines branching over module kinds).
  _Sev: Low · Risk: Med._

## Cleanup & docs

- [ ] **15 (R2) — Consolidate duplicated cache-root logic** between
  `module_cache.py` and `nsx_lock`. _Sev: Low · Risk: Low._
- [ ] **16 (R4) — Audit raw-OSError/ValueError leakage** past the `NSXError` CLI
  mediator (e.g. `shutil` copytree/rmtree, `from_mapping` parsing) against the
  "friendly failure" rule. _Sev: Med · Risk: Low._
- [ ] **17 (R3) — Inventory & document env escape hatches**
  (`NSX_SKIP_COMPAT_CHECK`, legacy-metadata shims) in AGENTS.md.
  _Sev: Low · Risk: Low._
- [ ] **18 (R5) — Document the schema break-and-fix policy** (lock/descriptor
  schema mismatch raises with no migration path). _Sev: Low · Risk: Low._
