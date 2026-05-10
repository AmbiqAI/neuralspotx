# neuralspotx (nsx) — Round-2 Architectural & Code Review

_Review date: 2026-05-10. Scope: post-R1–R25 state on `main`. Goals: stability across Windows/macOS/Linux, true library/CLI separation, programmatic-API completeness, recursive disclosure of complexity, no repeats of the original neuralSPOT's flakiness/odd-assumption pain._

## Executive Summary

The first round (R1–R25) closed all the structural critical bugs (typed errors, decomposed `operations/`, board→provider single-source-of-truth, fail-closed app lock, etc.). What remains is mostly a **layering and surface-area** problem, plus a small set of **Windows/locale fragilities** that will bite the moment we leave the macOS/UTF-8 happy path.

The four highest-leverage themes are:

1. **CLI bypasses the public API.** Every `cmd_*` in [src/neuralspotx/cli.py](src/neuralspotx/cli.py) calls `operations.*_impl` directly. That means `api.timeout_budget`, dataclass-request normalization, and exception translation only run for embedders — never for end-users. The CLI is in practice a *parallel implementation*, not a thin adapter.
2. **`print()` is the only output channel.** [src/neuralspotx/operations/](src/neuralspotx/operations) and [src/neuralspotx/tooling.py](src/neuralspotx/tooling.py#L77) write user-visible strings with bare `print()`. Library callers (helia-profiler, future GUIs, agents) cannot suppress, capture, redirect, or stream that output, and quiet/verbose flags do not really mean anything.
3. **Windows process-tree kill is a no-op.** [src/neuralspotx/subprocess_utils.py L90](src/neuralspotx/subprocess_utils.py#L90) only `proc.kill()`s the root on `os.name == "nt"`. CMake → ninja → compiler chains will leak on timeout/Ctrl-C. This is exactly the class of bug the legacy neuralSPOT was famous for.
4. **Locale/encoding assumptions still leak.** The R17 Windows-CI failure (em-dash + cp1252 default) was a symptom, not a cause. We do not have a `.gitattributes`, a pinned-encoding lint, or a non-UTF-8 CI lane, so the next contributor will rediscover the same bug.

The rest of this document is structured like the previous `REVIEW.md`: numbered, checkbox-style, file-linked, ordered roughly by leverage. Each item is sized to be one PR.

---

## A. Layering & API/CLI parity

- [ ] **A1. CLI must delegate through `api.*`, not `operations.*_impl`.** Every `cmd_*` in [src/neuralspotx/cli.py](src/neuralspotx/cli.py#L283) bypasses [src/neuralspotx/api.py](src/neuralspotx/api.py). Consequences today: `timeout_budget` is not applied on the CLI path, exception → exit-code mapping is duplicated, and dataclass-request validation runs only for embedders. Net: there are **two** behaviors of NSX. Move the CLI to construct `AppBuildRequest`/etc. and call `api.build_app(...)`.
- [ ] **A2. Make `print()` go through a structured emitter.** Introduce `nsx._io.Emitter` (or `logging` configured at CLI startup) and replace every `print(...)` in [src/neuralspotx/operations/](src/neuralspotx/operations) and [src/neuralspotx/tooling.py L77](src/neuralspotx/tooling.py#L77). API entry points should accept an optional `emit: Callable[[Event], None]` so embedders (helia-profiler) can capture events instead of stdout.
- [ ] **A3. Per-call verbosity, not process-global.** [src/neuralspotx/operations/_common.py](src/neuralspotx/operations/_common.py) (`set_verbosity`) and [src/neuralspotx/subprocess_utils.py L31](src/neuralspotx/subprocess_utils.py#L31) (`_VERBOSE`) are module globals. Use a `ContextVar` (same pattern as `_TIMEOUT` and `_resolve_cache.ttl_override`) so concurrent API callers don't trample each other.
- [ ] **A4. `doctor()` must return a typed result, not just print.** Today [src/neuralspotx/operations/_doctor.py L190](src/neuralspotx/operations/_doctor.py#L190) raises on failure and prints rows in between. Return `DoctorReport(checks: list[DoctorCheck], ok: bool)` and have the CLI render it. Embedders (CI scripts, helia, agents) can then act on the structured report.
- [ ] **A5. `lock_app` should return `NsxLock`, not `Path`.** [src/neuralspotx/api.py L755](src/neuralspotx/api.py#L755) returns the lock-file path; callers immediately re-`read_lock(path)`. Return the parsed object directly and keep the path on `lock.path`.
- [ ] **A6. `outdated_app` should return entries, not a count.** [src/neuralspotx/api.py L803](src/neuralspotx/api.py#L803) returns `int`; the JSON report lives only on stdout. Return `list[OutdatedModule]` (typed dataclass) and let the CLI/JSON renderer be one layer up.
- [ ] **A7. `add_module / remove_module / update_modules / register_module / init_module` should return change records.** They currently return `None` and only print. Return `ModuleChange{name, before, after, action: Literal["added"|"removed"|"updated"|"noop"]}` so embedders can build their own UX.
- [ ] **A8. Expose `cache info` / `cache clean` on `api`.** [src/neuralspotx/cli.py L666](src/neuralspotx/cli.py#L666) and [L697](src/neuralspotx/cli.py#L697) walk caches with helpers that don't exist on the public API. Add `api.cache_info() -> CacheInfo` and `api.clean_cache(...) -> CacheCleanResult`.
- [ ] **A9. `__init__.py` re-exports a subset; document or close the gap.** [src/neuralspotx/__init__.py](src/neuralspotx/__init__.py) does not re-export `LockKind` enum members usefully, `OutdatedStatus`, `ProfileStatus`, `CommandCategory`, `CommandScope`, `DoctorReport` (when added). Either expose them or write a SPEC for what is "public".
- [ ] **A10. Decompose `operations/_lock.py` (771 lines).** Split into `_lock/build.py` (`_build_lock_for_app`), `_lock/io.py` (read/write), `_lock/outdated.py` (`outdated_app_impl`). Same recipe as R25.

## B. Cross-platform robustness (Windows / non-UTF-8)

- [ ] **B1. Windows process-tree kill.** [src/neuralspotx/subprocess_utils.py L86–L106](src/neuralspotx/subprocess_utils.py#L86) calls only `proc.kill()` on Windows. Wrap children in a Win32 [Job Object](https://learn.microsoft.com/windows/win32/procthread/job-objects) (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) so timeouts and Ctrl-C kill the whole `cmake → ninja → cl` tree, the same guarantee POSIX gets via `setsid + killpg`. Without this, the legacy neuralSPOT's "ghost ninja" class of bugs returns.
- [x] **B2. Add `.gitattributes`.** Currently absent (we verified during R17). Add `* text=auto eol=lf` and explicit `*.cmake text eol=lf`, `*.py text eol=lf`. The CRLF/encoding hop that broke R17's drift test should be impossible to reintroduce.
- [ ] **B3. Pin `encoding="utf-8"` everywhere it is missing.** Audit complete: [scripts/gen_board_table.py](scripts/gen_board_table.py) and [tests/test_board_table_drift.py](tests/test_board_table_drift.py) were fixed; one-shot lint (e.g. `ruff` rule `PLW1514`) should make this a permanent invariant.
- [x] **B4. Add a non-UTF-8 CI lane.** Run unit tests once with `LC_ALL=C LANG=C` on Linux (cheap matrix entry). Catches every "default encoding" regression before it hits a Windows runner.
- [ ] **B5. Replace `os.path.join` mixing in `_doctor.py`.** [src/neuralspotx/operations/_doctor.py L73–L86](src/neuralspotx/operations/_doctor.py#L73) builds ATfE candidate paths with `os.path.join`/`os.path.isfile`. Use `pathlib` to match the rest of the codebase and pick up the `.exe`-suffix-on-Windows expansion `tooling.tool_path` already does.
- [ ] **B6. Make `extract_view_command` ninja-parser non-fragile.** [src/neuralspotx/subprocess_utils.py L324](src/neuralspotx/subprocess_utils.py#L324) scans a fixed window of `build.ninja` and shlex-splits with `posix=(os.name != "nt")`. Prefer `ninja -t commands <target>` (a documented contract), with the current parser as fallback only.
- [ ] **B7. JLink resolution: validate `JLink.exe` on Windows.** [src/neuralspotx/tooling.py L91](src/neuralspotx/tooling.py#L91) lists `JLinkExe`/`JLink`. On Windows the executable is `JLink.exe`; `tool_path` does add `.exe`/`.bat`/`.cmd` for in-venv lookup ([tooling.py L29](src/neuralspotx/tooling.py#L29)) but PATH-resolution relies on `shutil.which` + PATHEXT. Add an explicit Windows-only test for `cmd_doctor` finding `JLink.exe`.
- [ ] **B8. Path-length / long-path on Windows.** `examples/<app>/build_<board>/...` chains plus deeply vendored `modules/nsx-ambiqsuite-r5/sdk/...` already produce paths >200 chars. Document the `\\?\` opt-in or shorten `_nsx_pick_first_existing` outputs.

## C. Concurrency & cache integrity

- [ ] **C1. Inter-process lock around the JSON caches.** [src/neuralspotx/_resolve_cache.py L145](src/neuralspotx/_resolve_cache.py#L145) and [src/neuralspotx/nsx_lock.py L367](src/neuralspotx/nsx_lock.py#L367), [L380](src/neuralspotx/nsx_lock.py#L380) still do read-modify-write. Two concurrent `nsx lock` invocations (e.g. from helia-profiler model sweeps) will silently lose entries. Wrap each cache file with the same `app_lock`-style primitive (now in `file_lock.py`) keyed on the cache path.
- [ ] **C2. `parallel_map` exception swallowing.** [src/neuralspotx/operations/_lock.py L172–L188](src/neuralspotx/operations/_lock.py#L172) treats every prefetch exception as "skip". Fine for performance, bad for diagnosis. Surface a `--debug-prefetch` flag (or always `_log.debug` with the full traceback).
- [ ] **C3. `app_lock` reentrancy across threads.** [src/neuralspotx/file_lock.py L73](src/neuralspotx/file_lock.py#L73) tracks held paths in a `ContextVar` (good), but a multi-threaded embedder still has to call `app_lock` per thread. Document this clearly in the module docstring; add a thread-pool stress test.
- [ ] **C4. `git-artifact-hashes.json` schema versioning.** No `schema_version` key on the cache file; a future migration would need to nuke `~/.cache/nsx/` for every user. Add the version now while it's cheap.

## D. Performance & scaling

- [ ] **D1. `list_modules(include_metadata=True)` is the default.** [src/neuralspotx/api.py](src/neuralspotx/api.py) and [src/neuralspotx/cli.py L499](src/neuralspotx/cli.py#L499) always pay full metadata parse. Default to `False`; opt in for `nsx module describe`.
- [ ] **D2. Memoize registry parse per process.** [src/neuralspotx/module_discovery.py L283](src/neuralspotx/module_discovery.py#L283) and [src/neuralspotx/module_registry.py L621](src/neuralspotx/module_registry.py#L621) re-load the packaged registry on every call. `functools.lru_cache` on `_load_registry()` keyed by mtime would be free.
- [ ] **D3. `_dir_size_bytes` walks the cache for every `cache info` call.** [src/neuralspotx/cli.py L654](src/neuralspotx/cli.py#L654). Cache the previous size with mtime; refresh only when the cache root mtime moves.
- [ ] **D4. Generator `gen_board_table.py` is invoked manually.** Add a one-line pre-commit hook (`pre-commit-hooks/regenerate-board-table`) that runs the generator and `git add`s the result. Removes the "stale cmake" failure mode that R17 had to firefight.

## E. Public-API completeness

- [ ] **E1. Streaming subprocess output to API consumers.** Helia and future GUIs want a "tail of build output" channel, not stdout. Extend `api.build_app(..., on_line=callback)` and route `subprocess_utils.run` through the emitter from A2.
- [ ] **E2. Async API surface.** None today. A small `nsx.aio` module wrapping the sync API with `asyncio.to_thread` (the sync API is already thread-safe via ContextVars) costs <50 lines and unblocks integration with notebook/Streamlit profilers.
- [ ] **E3. Typed `nsx.yml` model.** [src/neuralspotx/project_config.py L28](src/neuralspotx/project_config.py#L28) is still `dict[str, Any]` end-to-end (R6 R7 didn't fully land). Convert `nsx.yml` to `pydantic` or `dataclass` model; map .get-chains to attribute access; surface validation errors at load time.
- [ ] **E4. Public `nsx_lock.NsxLock` is partial.** [src/neuralspotx/__init__.py](src/neuralspotx/__init__.py) exposes only `LockKind`; expose `NsxLock`, `ResolvedModule`, `OutdatedStatus` etc. Without them, any embedder that wants to inspect a lock has to import private modules.
- [ ] **E5. `--json` everywhere it makes sense.** `nsx outdated --json` exists; `nsx doctor`, `nsx module list`, `nsx cache info`, `nsx commands` should each take `--json`. Closes the loop with E1 — an agent should be able to drive nsx without parsing human prose.
- [ ] **E6. Programmatic project-creation does not return the new app's `find_app_root`.** [src/neuralspotx/api.py L237](src/neuralspotx/api.py#L237) returns `None`. Should return `Path` (the resolved app dir) so callers can chain `create_app → configure_app`.

## F. CMake layer

- [ ] **F1. `nsx_select_sdk_provider` provider-side branching.** After R17 the board → provider lookup is table-driven, but the per-provider root/version/target chooser ([nsx_sdk_providers.cmake L34–L74](src/neuralspotx/cmake/nsx_sdk_providers.cmake#L34)) is still an if/elseif chain. Generate a second table from a single Python source, mirroring R17.
- [ ] **F2. `nsx_toolchain_flags.cmake` should split per family.** Three large branches in one 150-line file; each is independently complex. Move to `toolchains/{gcc,armclang,atfe}.cmake` and `include()` based on `NSX_TOOLCHAIN_FAMILY`.
- [ ] **F3. Emit a CMake preset per app on `nsx configure`.** Today users cannot run `cmake --preset` — they have to invoke `nsx`. Generating `CMakePresets.json` from the configured board/toolchain enables every IDE (CLion, VS, vscode-cmake-tools) to drive builds natively.
- [ ] **F4. The `cmake/nsx/` vendored copy must be diffable.** Currently each app has its own copy of `nsx_sdk_providers.cmake`/`nsx_board_table.cmake`/`nsx_toolchain_flags.cmake` (three files × 8 examples = 24 copies). Vendoring is correct; **add a CI check** that diff-matches every example's `cmake/nsx/` against `src/neuralspotx/cmake/`. Stops the next R17-style drift before it ships.

## G. Recursive disclosure of complexity (UX)

- [ ] **G1. Tier `nsx --help` output.** Today every command is shown flat. Group as `Quickstart` (`doctor`, `create-app`, `configure`, `build`, `flash`), `Modules` (`module …`), `Maintenance` (`lock`, `sync`, `outdated`, `update`, `cache`), `Introspection` (`commands`, `module list/describe/search`).
- [ ] **G2. `nsx module` is overwhelming.** 8 subcommands at the same level. Promote `add` / `list` / `describe` to top-level (`nsx add`, `nsx list-modules`?), keep `module init/register/validate/update/remove` under `nsx module …` for power users.
- [ ] **G3. First-run guidance.** `nsx` with no args could detect "no app in cwd, no `~/.config/nsx/`" and print a 5-line tutorial pointing at `nsx doctor && nsx create-app my_app`. Today the bare `nsx` invocation prints argparse usage with 25 commands.
- [ ] **G4. `nsx doctor` should suggest the next concrete command.** Current output is OK/FAIL rows. Add: "Next: run `nsx create-app my_app` to verify your toolchain end-to-end."
- [ ] **G5. Explicit "compatibility" preview before a destructive op.** `nsx update` re-resolves every module to upstream tip. Print a one-line summary of what will move and require `--yes` (or interactive confirm) when more than N modules change.

## H. Quality / testing

- [ ] **H1. Test parity matrix CLI vs API.** For each public command, assert that `nsx <cmd>` and `nsx.api.<cmd>(...)` produce identical state. Catches every A1-class drift automatically.
- [ ] **H2. Property tests for `nsx.yml` parsing.** Use `hypothesis` to generate near-valid manifests; assert that loader either succeeds or raises `NSXConfigError` with a non-empty `path`/`reason`. This is the most common "weird crash" surface for end-users.
- [ ] **H3. Nightly `test_example_builds` on all three OSes.** It is currently `--ignore`d in the default unit-test pass and only the `example-builds` workflow runs the real toolchain. Add a scheduled run that also exercises `nsx flash`/`nsx view` in mock mode.
- [ ] **H4. Performance regression budget.** `lock` + `sync` end-to-end on a fresh cache should be <X seconds; `lock` re-run with warm cache <Y seconds. Track in CI; fail PRs that regress >25%.
- [ ] **H5. Concurrency stress test.** Spawn N parallel `nsx lock --check` against the same app; expect zero lost cache writes (covers C1) and zero lock-primitive errors (covers C3).

## I. Security & supply chain

- [ ] **I1. Pin `git -c protocol.allow=...` for module clones.** `git_clone_at_commit` (in `nsx_lock.py`) clones arbitrary URLs from a registry that may be edited by app authors. At minimum disable `ext::` and `file::` protocols by default.
- [ ] **I2. Verify lock-file content hash matches vendored tree on `sync --frozen`.** I believe this is partially covered ("frozen" mode in `sync_app_impl`); add a test that proves a malicious mid-tree edit is rejected.
- [ ] **I3. SBOM emission.** `nsx lock` already records every module's resolved commit + content hash. One small command — `nsx sbom --format spdx` — converts that to a CycloneDX/SPDX file. Cheap to add now; impossible to retrofit cleanly later.

---

## J. Code organization & readability (human-friendliness)

The codebase shows signs of incremental agent assembly: lots of `_underscore_helpers`, free functions where a small class would carry the same context, and stringly-typed registries where a dataclass would document intent. These items target *legibility* — a new contributor should be able to navigate the code without grepping for which `_foo_helper` belongs to which concern.

- [x] **J1. Replace ad-hoc `print()` with `logging`.** Configure the root `nsx` logger in `cli.py` (level driven by `-v`/`-vv`/`-q`); replace every `print()` in [src/neuralspotx/operations/](src/neuralspotx/operations), [src/neuralspotx/tooling.py L77](src/neuralspotx/tooling.py#L77), [src/neuralspotx/cli.py L257](src/neuralspotx/cli.py#L257) onward, [src/neuralspotx/nsx_lock.py L291](src/neuralspotx/nsx_lock.py#L291), [src/neuralspotx/subprocess_utils.py L186](src/neuralspotx/subprocess_utils.py#L186) with `logger.info` / `logger.debug` / structured records. (Subsumes A2 and is a precondition for E1.) Use `logging.handlers.QueueHandler` so embedders can attach their own sink.
- [ ] **J2. Promote frequent `_helpers` into focused classes.** Examples:
    - `_module_discovery_record(s)`, `_print_module_table`, `_module_record` ([src/neuralspotx/module_registry.py](src/neuralspotx/module_registry.py)) → a `ModuleCatalog` object that holds the registry, exposes `.list()`, `.describe()`, `.search()`, `.print_table()`.
    - `_load_app_cfg`, `_save_app_cfg`, `_effective_registry`, `_write_app_module_file`, `_write_modules_gitignore`, `_module_clone_dir`, `_vendored_target_dir`, `_copy_packaged_tree`, `_registry_project_entry`, `_nsx_tool_version` ([src/neuralspotx/project_config.py](src/neuralspotx/project_config.py)) → an `AppProject` class that owns `app_dir` and the parsed `nsx.yml`.
    - `_build_lock_for_app`, `_resolved_module_path`, `hash_git_artifact`, `hash_manifest`, `hash_tree`, `read_lock`, `write_lock`, `resolve_ref`, `resolve_commit` → a `LockBuilder` orchestrator on top of an `NsxLock` data class.
- [ ] **J3. Restructure `_COMMAND_GRAPH_HINTS` ([src/neuralspotx/cli.py L36](src/neuralspotx/cli.py#L36)).** A 100-line literal `dict[str, CommandHint]` keyed by space-joined command paths is fragile and unreadable. Replace with one of:
    - declare `next_commands` as a tuple on each `cmd_*` function via a decorator (`@nsx_cmd(category=BUILD, scope=APP, next=("build","flash","view"))`), and let argparse-walk discover it; or
    - move the table to `data/command_graph.yaml` and load it at startup with schema validation.
   Either approach co-locates the hint with the command and removes the magic-string key.
- [ ] **J4. Adopt Google-style docstrings consistently.** A spot check across [src/neuralspotx/api.py](src/neuralspotx/api.py), [src/neuralspotx/operations/](src/neuralspotx/operations), [src/neuralspotx/cli.py](src/neuralspotx/cli.py), [src/neuralspotx/module_registry.py](src/neuralspotx/module_registry.py) shows mixed styles (numpy-ish, freeform, missing). Add `pydocstyle` (Google convention) to pre-commit; one cleanup PR per file family. Required sections per public callable: `Args:`, `Returns:`, `Raises:`, `Example:` where useful.
- [ ] **J5. Decompose oversize files.** Concrete targets (post-R25):
    - [src/neuralspotx/cli.py](src/neuralspotx/cli.py) (1239) → `cli/{__init__.py, app.py, modules.py, cache.py, doctor.py, parser.py, render.py}`. Subsumes A1.
    - [src/neuralspotx/module_registry.py](src/neuralspotx/module_registry.py) (860) → split discovery (read-only lookups) from mutation (modify `nsx.yml` registry overrides).
    - [src/neuralspotx/api.py](src/neuralspotx/api.py) (844) → keep request dataclasses in `api/_models.py`, public callables in `api/__init__.py`.
    - [src/neuralspotx/operations/_lock.py](src/neuralspotx/operations/_lock.py) (771) → see A10.
    - [src/neuralspotx/nsx_lock.py](src/neuralspotx/nsx_lock.py) (675) → split persistence (`NsxLock` model + I/O) from network (`resolve_ref` / `git_clone_at_commit`).
- [ ] **J6. Module-level header docstrings.** Many modules dive straight into imports without any "this file is responsible for …" preamble. Add a 5–15 line docstring at the top of each `src/neuralspotx/*.py` that names the module's responsibility, primary public symbols, and what *not* to put here.
- [ ] **J7. Reduce free functions in favor of small dataclasses with methods.** Where a free function takes the same 3–4 args repeatedly (`app_dir`, `nsx_cfg`, `registry`, `module_name`), promote them to methods on `AppProject` / `Module` / `LockBuilder`. Eliminates threading the same args through call chains and gives autocompletion a meaningful surface.
- [ ] **J8. Add an architecture diagram.** [docs/](docs) currently has no top-down picture of the data flow `nsx.yml → registry → resolution → lock → sync → vendored modules → cmake bootstrap`. A one-page Mermaid diagram in `docs/architecture.md` (rendered via mkdocs) would orient new contributors in 30 seconds.
- [ ] **J9. Audit `# noqa: BLE001` and `except Exception:`.** Each instance ([src/neuralspotx/file_lock.py L84,L108,L163](src/neuralspotx/file_lock.py#L84), [src/neuralspotx/operations/_lock.py L485](src/neuralspotx/operations/_lock.py#L485), [_resolve_cache.py L149](src/neuralspotx/_resolve_cache.py#L149), [nsx_lock.py L329,L451](src/neuralspotx/nsx_lock.py#L329)) should either narrow the exception or carry a one-line justification. Codify with `ruff` rule `BLE001` enabled globally + per-line `# noqa: BLE001 — <reason>`.

## Out of scope for this round (deliberately deferred)

- Whole-project rewrite to Click/Typer for the CLI (current `argparse` works; G1/G2 are cheaper).
- Switching from `uv` to `poetry` or vice versa.
- Adopting a runtime config file (`~/.config/nsx/config.toml`) — defer until E1/E2 land and we know what users actually configure.

## How to use this document

Same recipe as REVIEW.md: pick the highest-leverage unchecked item, branch, implement, PR, squash-merge, mark `[x]`. The items are intentionally one-PR-sized.

Suggested ordering (highest leverage first):

1. **B2 + B4** (.gitattributes + non-UTF-8 CI) — cheap, permanent, closes R17 class.
2. **J1** (logging) — subsumes A2; precondition for streaming output, quiet/verbose to mean anything, and embedder log capture.
3. **A3** (per-call verbosity via ContextVar) — pairs with J1.
4. **B1** (Windows process-tree kill) — eliminates the legacy-neuralSPOT "ghost ninja" failure class.
5. **F4** (vendored cmake diff CI) — closes R17 drift class permanently.
6. **A1** + **J5** (CLI → API; decompose `cli.py`) — done together; unlocks every other A-item.
7. **C1** (cache locking) — silent data loss is the worst kind.
8. **A4–A8** (typed return values from doctor / lock / outdated / module ops).
9. **J2 + J3** (helper → class promotion; restructure command-graph hints).
10. **J4 + J6 + J9** (docstring style, module headers, exception audit) — cleanup PRs that improve human readability.
