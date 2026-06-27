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
- [x] **6 (B6) — Validate SoC inventory symmetry.** `atomiq110` SoC facts exist
  with no NSX board; naming diverges (`apollo510L` vs `apollo510dL_evb`). Add a
  fast Python-level check that every board's `soc` resolves to an existing SDK
  facts file instead of failing late at CMake configure. _Sev: Med · Risk: Low._
  - Done: added `test_soc_inventory_symmetry` to
    `tests/test_board_cpu_facts_contract.py` (skip-if-absent). It checks both
    directions of the board↔SoC-facts inventory, matching by `soc` so name
    divergences like `apollo510dL_evb` → `apollo510L` are handled. **board →
    facts** is a hard requirement (a missing facts file is caught in Python/CI
    instead of failing late inside `nsx_load_soc_facts("…")` at CMake configure).
    **facts → board** is allow-listed via `ALLOWED_SOCS_WITHOUT_BOARD`
    (currently `{atomiq110}` — AT110 is FPGA bring-up / in development with no
    production EVB yet), so a new boardless SoC introduced by an SDK update is
    surfaced for review rather than silently accumulating. A configure-time
    runtime guard was considered but deferred: doctor has no SDK context and
    locating the vendored facts dir pre-CMake needs more module-resolution
    plumbing than this Low-risk item warrants.

## Board-name & provider hardening

- [x] **7 (B4) — Harden mixed-case load-bearing identifiers.** `apollo510dL_evb`
  → `apollo510L`, `apollo330mP_evb` → `apollo330P`. Case quirks thread through
  dirs, CMake target names, and package names while only input boundaries are
  lowercased. Normalize internal string-equality or document the invariant.
  _Sev: Med · Risk: Med._
  - Done: documented the authoritative case invariant in
    `src/neuralspotx/constants.py`: board / SoC names have a single canonical
    internal spelling, case-insensitivity is confined to input boundaries, and
    lowercasing is also a downstream join key (`_BOARD_LOOKUP`, `_board_lc`,
    `nsx-board-…` module names). Added a registry guard that reports canonical
    board/SoC names which would collide under case-folding, plus tests that pin
    uniqueness under case-folding and verify `validate_board_registry()` flags
    an injected collision instead of silently dispatching to the wrong board.
- [x] **8 (B5) — Decide on the single-valued SDK-provider abstraction.**
  `SDKProvider` has one member; `nsx_board_table.cmake` is a 15-branch dispatch
  that always returns `"ambiqsuite"`; module gate requires
  `support.ambiqsuite=true`. Either simplify to a single helper (delete per-board
  branches) or document the intended multi-vendor contract. Replace the regex
  parse of `board.cmake` text in `nsx_sdk_providers.cmake` with a parent field
  read from `board.yaml`. _Sev: Med · Risk: Med._
  - Done: simplified the CMake-side contract to the current reality: the
    generated `nsx_board_table.cmake` now carries the registered-board inventory
    (case-insensitive membership) instead of a fake 15-branch board→provider
    dispatch that always returned `ambiqsuite`, and `nsx_select_sdk_provider()`
    sets `NSX_SDK_PROVIDER=ambiqsuite` once a board resolves to a registered EVB.
    For custom boards, provider inference now follows `inherits:` from
    `board.yaml` rather than regex-parsing `NSX_PARENT_BOARD` out of generated
    `board.cmake` text. Kept `sdk_provider` first-class on the Python side
    (`board.yaml`, descriptors, CLI/API) and added tests that pin the current
    single-valued invariant plus a CMake-level regression proving `board.yaml`
    wins over conflicting `board.cmake` text.

## Layering refactors (ascending risk)

- [x] **9 (L5) — Make the hardcoded default board configurable.**
  `board="apollo510_evb"` in `api/_app.py` (~L30) and
  `operations/_app_lifecycle.py` (~L80). _Sev: Low · Risk: Low._
  - Done: introduced `constants.DEFAULT_BOARD` as the single configuration
    point for create-app defaults and threaded it through the typed request
    dataclass, the public API wrapper, and the lifecycle implementation. Added
    an API-dispatch regression test pinning that `create_app()` without an
    explicit board passes the canonical default through unchanged, so these
    three call sites cannot silently drift again.
- [x] **10 (L4) — Fold `init_module_impl`'s 11 args into a request dataclass**
  (`operations/_app_lifecycle.py` ~L225); the codebase already uses request
  dataclasses elsewhere. _Sev: Low · Risk: Low._
  - Done: moved the existing `ModuleInitRequest` DTO down into the neutral
    `models` layer (re-exported from `api` so the public import paths are
    unchanged) and made `init_module_impl` accept that single request object.
    Operations now consumes the request without importing the `api` layer and
    without re-declaring the field list, so there is no new drift hazard between
    a public DTO and an internal copy. Updated the dispatch and typed-exception
    tests to construct/inspect the request directly.
- [x] **11 (L6) — Replace ad-hoc dicts with dataclasses** where AGENTS.md asks for
  typed models: registry metadata `dict[str, Any]`
  (`module_registry/_metadata.py` ~L141) with nested `["support"]["ambiqsuite"]`
  indexing; `AppConfig.raw` (`models/_project.py` ~L365). _Sev: Med · Risk: Med._
  - Done (registry metadata): introduced a `ModuleMetadata` facade
    (`models/_module_metadata.py`) that wraps the *already-validated* metadata
    mapping and exposes the load-bearing structural fields as typed properties
    (`module_type`, `supports_ambiqsuite`, `required_deps`, `compatibility`,
    `required_sdk_provider`). `_load_module_metadata` now returns it, so the
    closure resolver, dependency policies, and reverse-dependency walk stop
    hand-indexing `meta["support"]["ambiqsuite"]` / `meta["depends"]["required"]`.
    The open-ended discovery/semantic payload (`capabilities`, `agent_keywords`,
    `constraints`, ...) deliberately stays in `.raw` so newly authored keys keep
    flowing through unchanged — typing the structure without freezing the
    extensible parts.
  - Reviewed & intentionally deferred (`AppConfig.raw`): `AppConfig` is already a
    frozen dataclass whose `raw.get(...)` access is fully encapsulated behind
    typed properties (no caller indexes `.raw`), and `.raw` is the source of
    truth for `nsx.yml` round-trip serialization. `nsx.yml` is user-authored and
    forward-compatible, so replacing `.raw` with nested dataclasses would risk
    dropping unknown keys on save and freeze a deliberately-open schema — a net
    loss of flexibility. Left as-is by design.
- [x] **12 (L1) — Move `board create` out of the CLI.** Logic lives in
  `cli/_cmd_board.py` (~L80) instead of `operations/`/`api/`; it's the one
  command that bypasses the stack. Push it down so the API can offer programmatic
  board creation. _Sev: Med · Risk: Med._
  - Done: extracted the scaffolding logic into `operations.create_board_impl`
    (new `operations/_board.py`) and exposed `api.create_board` (new
    `api/_board.py`) plus a typed `BoardCreateRequest`. The CLI handler
    `cmd_board_create` is now a thin shim that delegates to `api.create_board`
    (no-op emitter in `--json` mode). `create_board`/`BoardCreateRequest` are
    re-exported from `neuralspotx.api` and the top-level package and documented
    in `docs/reference/public-api.md`. Board creation is now programmatic and
    flows through the standard api → operations stack like every other command.
- [x] **13 (L2) — Separate dependency computation from acquisition.**
  `_resolve_module_closure` triggers side-effectful `_acquire_modules_for_app`
  mid-DFS (`module_registry/_closure.py` ~L98). Split for testability and
  dry-run correctness. _Sev: Med · Risk: Med._
  - Reviewed & intentionally kept the flag-gated design (documented in place).
    The acquire/compute interleaving is *intrinsic*: a module's dependencies
    live inside its own `nsx-module.yaml`, so the graph can only be discovered
    incrementally (fetch → parse → expand); a literal "compute the full closure,
    then acquire" is impossible without repeated resolve passes (more side-effect
    surface, not less). A clean injected-acquirer split was also rejected because
    the `local`/`vendored` module-name sets are computed *once* in the resolver
    and serve both traversal-skipping and acquisition — pulling acquisition out
    would duplicate that computation in callers (a single-source-of-truth
    regression) for marginal gain. The existing `acquire_missing` flag is the
    right-sized seam; added an explanatory comment at the acquisition site so the
    intrinsic coupling is self-documenting. Dry-run/read-only resolution already
    works via `acquire_missing=False` with the locked-closure fallback in
    `operations/_lock.py`.
- [x] **14 (L3) — Decompose the `_sync_app_impl_unlocked` god function**
  (`operations/_sync.py` ~L125, 200+ lines branching over module kinds).
  _Sev: Low · Risk: Med._
  Done: extracted a frozen `_SyncContext` (app_dir/registry/cmake_nsx/frozen/force)
  plus per-kind handlers — `_resolve_vendored_dir`, `_sync_vendored_entry`,
  `_sync_unresolved_entry`, `_verify_duplicate_path`, `_sync_local_entry`,
  `_sync_fetchable_entry` — leaving `_sync_app_impl_unlocked` as a slim
  preamble→dispatch→postamble orchestrator. Strictly behavior-preserving: all
  branch order, error messages, and comments retained; covered by
  `tests/test_nsx_lock.py` (frozen/force/local-source-drift/no-op/fresh-checkout).

## Cleanup & docs

- [x] **15 (R2) — Consolidate duplicated cache-root logic** between
  `module_cache.py` and `nsx_lock`. _Sev: Low · Risk: Low._
  Done: the `NSX_CACHE_DIR`/`XDG_CACHE_HOME`/`~/.cache` resolution was duplicated
  in *three* places (`module_cache._nsx_cache_root`, `nsx_lock._hashing.
  _git_artifact_hash_cache_path`, `_resolve_cache._cache_path`). Extracted a
  stdlib-only leaf `_cache_paths.nsx_cache_root()` (no intra-package imports, so
  no cycle risk) as the single source of truth; all three call sites now derive
  their per-cache file paths from it. Behavior-preserving.
- [x] **16 (R4) — Audit raw-OSError/ValueError leakage** past the `NSXError` CLI
  mediator (e.g. `shutil` copytree/rmtree, `from_mapping` parsing) against the
  "friendly failure" rule. _Sev: Med · Risk: Low._
  Done: audited every CLI handler path. Core config (`project_config`) and the
  cache readers were already well-guarded. Hardened the genuine leaks for **both**
  the CLI and programmatic surfaces: (1) the subprocess chokepoint
  `subprocess_utils._runner` now wraps `Popen` so a missing executable
  (`cmake`/`ninja`/`git` not on PATH) raises a typed `NSXToolchainError` instead
  of a raw `FileNotFoundError` — covers all build/lock/sync/git spawns; (2)
  `nsx_lock._io.read_lock_file` wraps `OSError`/`yaml.YAMLError`/`ValueError`
  (e.g. an `nsx.lock` with unresolved merge-conflict markers) into a typed
  `NSXLockError`, letting the already-typed schema-mismatch error pass through;
  (3) added a verbose-gated `except OSError` backstop to the CLI `main()` so any
  residual environmental/permission failure produces a friendly `error: …` exit
  instead of a traceback. New regression tests in `tests/test_error_mediation.py`.
  Left metadata's internal `ValueError` validation contract intact (callers like
  `api/_modules` already translate it).
- [ ] **17 (R3) — Inventory & document env escape hatches**
  (`NSX_SKIP_COMPAT_CHECK`, legacy-metadata shims) in AGENTS.md.
  _Sev: Low · Risk: Low._
- [ ] **18 (R5) — Document the schema break-and-fix policy** (lock/descriptor
  schema mismatch raises with no migration path). _Sev: Low · Risk: Low._
