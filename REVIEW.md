# neuralspotx (nsx) — Architectural & Code Review

_Review date: 2026-05-07. Scope: `neuralspotx/src/neuralspotx/` Python package, packaged CMake layer, scripts, tests, and stated-intent docs (README, AGENTS). Goal: stability, robustness, performance, API cleanliness, and reducing dict/string smells in favor of dataclasses/enums._

## Executive Summary

1. **Critical correctness:** local/vendored module normalization is asymmetric — vendored modules can be silently rewritten through registry-only paths during module-set rewrites, breaking remove/update flows. See [src/neuralspotx/module_registry.py](src/neuralspotx/module_registry.py#L686) and [L611](src/neuralspotx/module_registry.py#L611).
2. **Critical robustness:** YAML root type is not validated in app-config loading; malformed/empty `nsx.yml` crashes with `AttributeError` instead of an actionable error. See [src/neuralspotx/project_config.py L109](src/neuralspotx/project_config.py#L109), [L434](src/neuralspotx/project_config.py#L434).
3. **Critical concurrency:** API lock TTL override mutates process-global env state, leaking across concurrent callers. See [src/neuralspotx/api.py L762](src/neuralspotx/api.py#L762).
4. **Critical safety gap:** app lock is fail-open on lock-primitive errors — proceeds without synchronization in the highest-risk paths (lock/sync/update). See [src/neuralspotx/file_lock.py L77](src/neuralspotx/file_lock.py#L77).
5. **Architecture drift:** CLI is not consistently a thin adapter to API; several commands bypass API and skip shared timeout/error normalization. See AGENTS [L62](AGENTS.md#L62) vs CLI [L340](src/neuralspotx/cli.py#L340), [L388](src/neuralspotx/cli.py#L388), [L432](src/neuralspotx/cli.py#L432), [L620](src/neuralspotx/cli.py#L620).
6. **Diagnostics:** `doctor` can return false-OK for J-Link runtime when probe exits non-zero but doesn't match a narrow hint pattern. See [src/neuralspotx/operations.py L449](src/neuralspotx/operations.py#L449).
7. **Cache concurrency:** caches are atomic per write but read-modify-write without inter-process coordination — concurrent writers can drop entries. See [src/neuralspotx/_resolve_cache.py L145](src/neuralspotx/_resolve_cache.py#L145), [src/neuralspotx/nsx_lock.py L367](src/neuralspotx/nsx_lock.py#L367), [L380](src/neuralspotx/nsx_lock.py#L380).
8. **Performance:** module discovery/search re-deserializes metadata for entire registries on every call. See [src/neuralspotx/module_discovery.py L283](src/neuralspotx/module_discovery.py#L283).
9. **Tests:** strong on lock mechanics; thin on malformed-config paths, CLI/API parity, and cache concurrency. See [tests/](tests).
10. **CMake:** coherent and modular at top level, but toolchain/provider selection still relies on stringly-typed globals and board-name branching that mirrors Python-side string maps. See [src/neuralspotx/cmake/nsx_app_bootstrap.cmake](src/neuralspotx/cmake/nsx_app_bootstrap.cmake#L1), [nsx_sdk_providers.cmake](src/neuralspotx/cmake/nsx_sdk_providers.cmake#L1), [nsx_toolchain_flags.cmake](src/neuralspotx/cmake/nsx_toolchain_flags.cmake#L1).

---

## Architecture Assessment

Layering in practice:

1. **Data/helpers:** `metadata`, `models`, `project_config`, `tooling`, `subprocess_utils`, lock/cache helpers.
2. **Orchestration:** `operations`.
3. **API:** typed requests + conversion wrappers in `api`.
4. **CLI:** `argparse` and command dispatch in `cli`.
5. **CMake runtime:** packaged app bootstrap/toolchain/provider files consumed by generated apps.

### Layering issues

1. **CLI does not consistently delegate to API.** Several commands call `operations` directly, splitting behavior and undermining API as the stable surface:

   ```python
   operations.create_app_impl(...)
   operations.view_app_impl(...)
   n = operations.outdated_app_impl(...)
   ```
   Evidence: [src/neuralspotx/cli.py L340](src/neuralspotx/cli.py#L340), [L388](src/neuralspotx/cli.py#L388), [L432](src/neuralspotx/cli.py#L432).

2. **AGENTS contract** says CLI should stay thin and delegate, but module subcommands bypass API almost entirely:

   ```python
   operations.add_module_impl(...)
   operations.register_module_impl(...)
   ```
   Evidence: [AGENTS.md L73](AGENTS.md#L73), [src/neuralspotx/cli.py L620](src/neuralspotx/cli.py#L620), [L646](src/neuralspotx/cli.py#L646).

3. **API depends on `operations` raising `SystemExit`** and normalizes at the wrapper boundary, so internal library behavior remains CLI-centric rather than exception-typed and domain-centric.

4. **CMake/Python duplication.** Provider/toolchain logic duplicates board/toolchain mapping semantics in Python constants and CMake conditionals, increasing drift risk. Evidence: [src/neuralspotx/constants.py L1](src/neuralspotx/constants.py#L1), [src/neuralspotx/cmake/nsx_sdk_providers.cmake L10](src/neuralspotx/cmake/nsx_sdk_providers.cmake#L10).

---

## Critical Bugs

1. **Malformed `nsx.yml` crashes with `AttributeError`** instead of a controlled error.
   Evidence: [src/neuralspotx/project_config.py L109](src/neuralspotx/project_config.py#L109), [L434](src/neuralspotx/project_config.py#L434)
   ```python
   return yaml.safe_load(path.read_text(encoding="utf-8"))
   if cfg.get("schema_version") != 1:
   ```
   A non-mapping YAML root (null/list/scalar) breaks before any user-friendly validation.

2. **Vendored modules treated as opaque in closure but not preserved in config rewrite.**
   Evidence: [src/neuralspotx/module_registry.py L611](src/neuralspotx/module_registry.py#L611), [L686](src/neuralspotx/module_registry.py#L686)
   ```python
   if module_name in opaque_names:
       resolved.append(module_name)
   ...
   else:
       new_modules.append(_module_record(name, registry))
   ```
   Vendored entries can be rewritten into registry records or fail when not in registry.

3. **Global env mutation for per-call TTL is race-prone.**
   Evidence: [src/neuralspotx/api.py L762](src/neuralspotx/api.py#L762)
   ```python
   _prev_ttl = os.environ.get(_ttl_env_key)
   os.environ[_ttl_env_key] = str(request.resolve_ttl_s)
   ```
   Concurrent API callers can leak TTL settings into each other.

4. **App lock fail-open on locking errors** can allow data races in lock/sync/update.
   Evidence: [src/neuralspotx/file_lock.py L77](src/neuralspotx/file_lock.py#L77)
   ```python
   except Exception as exc:
       _warn_once(f"file lock unavailable ({exc}); proceeding without it.")
   ```
   The exact condition where the lock matters most proceeds unlocked.

5. **CLI `outdated` bypasses API timeout budgeting and has no `--timeout`.**
   Evidence: [src/neuralspotx/cli.py L432](src/neuralspotx/cli.py#L432), [L980](src/neuralspotx/cli.py#L980), [src/neuralspotx/operations.py L2043](src/neuralspotx/operations.py#L2043)
   ```python
   n = operations.outdated_app_impl(...)
   ...
   return resolve_commit(job[0], job[1]), None
   ```
   Network hangs in `git ls-remote` can block indefinitely.

6. **Doctor reports J-Link runtime OK on `CalledProcessError`** unless specific hint text matches.
   Evidence: [src/neuralspotx/operations.py L449](src/neuralspotx/operations.py#L449)
   ```python
   except subprocess.CalledProcessError as exc:
       ...
       all_ok &= _doctor_check("SEGGER J-Link runtime", True, ...)
   ```
   False-positive diagnostics reduce trust and slow troubleshooting.

7. **Resolve cache uses read-modify-write without locking;** concurrent puts drop entries.
   Evidence: [src/neuralspotx/_resolve_cache.py L145](src/neuralspotx/_resolve_cache.py#L145)
   ```python
   entries = _read_cache()
   entries[key] = (sha, kind, now)
   _write_cache(entries)
   ```

8. **Artifact-hash cache has the same lost-update pattern under concurrency.**
   Evidence: [src/neuralspotx/nsx_lock.py L367](src/neuralspotx/nsx_lock.py#L367), [L380](src/neuralspotx/nsx_lock.py#L380)
   ```python
   cache = _read_artifact_hash_cache()
   ...
   _write_artifact_hash_cache(cache)
   ```

9. **Parallel prefetch swallows broad exceptions and silently degrades,** then redoes the work serially.
   Evidence: [src/neuralspotx/operations.py L1243](src/neuralspotx/operations.py#L1243), [L1287](src/neuralspotx/operations.py#L1287)
   ```python
   except Exception:
       return None
   ```
   Hides root cause and increases latency/noise.

10. **Partial `create_app` failures are not rolled back;** app directory and side effects can be left inconsistent.
    Evidence: [src/neuralspotx/operations.py L192](src/neuralspotx/operations.py#L192)
    ```python
    _acquire_modules_for_app(app_dir, seed_modules, registry)
    ...
    _save_app_cfg(app_dir, nsx_cfg)
    ```
    Interrupted/failed bootstrap leaves half-generated app state with no recovery marker.

---

## Robustness Issues

1. **Library internals raise `SystemExit` pervasively,** making API embedding brittle outside CLI contexts. Evidence: [src/neuralspotx/operations.py L140](src/neuralspotx/operations.py#L140), [src/neuralspotx/module_registry.py L597](src/neuralspotx/module_registry.py#L597).
2. **`run_capture` timeout recovery suppresses secondary `communicate` errors broadly,** losing diagnostic detail. Evidence: [src/neuralspotx/subprocess_utils.py L154](src/neuralspotx/subprocess_utils.py#L154).
3. **`extract_view_command` depends on a fixed short scan window in `build.ninja`** and can break on generator formatting changes. Evidence: [src/neuralspotx/subprocess_utils.py L324](src/neuralspotx/subprocess_utils.py#L324).
4. **Lock/cache file ops are best-effort and suppress many I/O errors.** Smoothes UX but can hide persistent environment faults. Evidence: [src/neuralspotx/_resolve_cache.py L112](src/neuralspotx/_resolve_cache.py#L112), [src/neuralspotx/nsx_lock.py L409](src/neuralspotx/nsx_lock.py#L409).
5. **`app_lock` reentrancy tracking is a process-global set without threading guard;** thread-heavy embedders could race on `_held_paths` bookkeeping. Evidence: [src/neuralspotx/file_lock.py L95](src/neuralspotx/file_lock.py#L95).
6. **`_normalize_module_source` mutates loaded config in-memory without writeback semantics,** making behavior depend on call sequencing. Evidence: [src/neuralspotx/project_config.py L441](src/neuralspotx/project_config.py#L441).
7. **`view` command does not pass through API timeout wrapper,** unlike build/configure/flash/clean/update/lock/sync. Evidence: [src/neuralspotx/cli.py L388](src/neuralspotx/cli.py#L388), [src/neuralspotx/api.py L421](src/neuralspotx/api.py#L421).
8. **`doctor` checks external tools with hardcoded 10s timeout;** no user override for slow environments. Evidence: [src/neuralspotx/operations.py L436](src/neuralspotx/operations.py#L436).

---

## Performance Issues

1. **`search_modules` scans and loads metadata for every module on every query.** Evidence: [src/neuralspotx/module_discovery.py L299](src/neuralspotx/module_discovery.py#L299)
   ```python
   for record in _module_discovery_records(..., include_metadata=True):
   ```
2. **`list_modules` defaults `include_metadata=True`,** so even simple listings pay parse/validation cost. Evidence: [src/neuralspotx/module_discovery.py L234](src/neuralspotx/module_discovery.py#L234).
3. **Resolve-cache get/put reads the whole JSON file per call;** scales poorly with many module refs. Evidence: [src/neuralspotx/_resolve_cache.py L129](src/neuralspotx/_resolve_cache.py#L129), [L145](src/neuralspotx/_resolve_cache.py#L145).
4. **Artifact-hash cache** does full-file JSON I/O per hash lookup and write. Evidence: [src/neuralspotx/nsx_lock.py L367](src/neuralspotx/nsx_lock.py#L367), [L380](src/neuralspotx/nsx_lock.py#L380).
5. **`lock` prefetch does expensive parallel work** but may repeat it in the main loop when prefetch swallowed errors. Evidence: [src/neuralspotx/operations.py L1243](src/neuralspotx/operations.py#L1243), [L1297](src/neuralspotx/operations.py#L1297).
6. **Module metadata loading is repeatedly invoked across closure/dependents/discovery paths** without shared memoization at operation scope. Evidence: [src/neuralspotx/module_registry.py L621](src/neuralspotx/module_registry.py#L621), [L676](src/neuralspotx/module_registry.py#L676).
7. **Cache-info size calculation recursively walks every file for every request;** expensive on large caches. Evidence: [src/neuralspotx/cli.py L707](src/neuralspotx/cli.py#L707), [L742](src/neuralspotx/cli.py#L742).

---

## Type-Safety / Dict-and-String Smells

1. **Lock kind is stringly-typed** instead of an enum.
   Evidence: [src/neuralspotx/nsx_lock.py L121](src/neuralspotx/nsx_lock.py#L121)
   ```python
   kind: str  # "git" | "packaged" | "local" | "vendored" | "unresolved"
   ```
   Suggested: `LockKind` enum.

2. **Module search and discovery records are dict blobs.** Evidence: [src/neuralspotx/module_discovery.py L283](src/neuralspotx/module_discovery.py#L283). Suggested: `ModuleRecord` + `SearchMatch` dataclasses.

3. **`resolve_module_context` returns a tuple with a magic scope string.** Evidence: [src/neuralspotx/module_discovery.py L30](src/neuralspotx/module_discovery.py#L30). Suggested: `ModuleContext` dataclass + `Scope` enum.

4. **CLI command graph hints are nested dict-of-dict with category/scope string literals.** Evidence: [src/neuralspotx/cli.py L32](src/neuralspotx/cli.py#L32). Suggested: `CommandHint` dataclass, `CommandCategory` and `CommandScope` enums.

5. **Outdated status is a raw string.** Evidence: [src/neuralspotx/operations.py L2081](src/neuralspotx/operations.py#L2081). Suggested: `OutdatedStatus` enum.

6. **Project/registry configs are almost entirely `dict[str, Any]`.** Evidence: [src/neuralspotx/project_config.py L28](src/neuralspotx/project_config.py#L28). Suggested: `AppConfig`, `ModuleRegistryOverride`, `ModuleSource` dataclasses.

7. **Module metadata validation manipulates raw nested dicts with string keys throughout.** Evidence: [src/neuralspotx/metadata.py L84](src/neuralspotx/metadata.py#L84). Suggested: typed metadata schema model for internal use after parsing.

8. **`module_type` remains free-form string in API and operations.** Evidence: [src/neuralspotx/api.py L201](src/neuralspotx/api.py#L201), [src/neuralspotx/operations.py L241](src/neuralspotx/operations.py#L241). Suggested: `ModuleType` enum reused from metadata constants.

9. **`profile_status` compared as magic string.** Evidence: [src/neuralspotx/operations.py L208](src/neuralspotx/operations.py#L208). Suggested: `ProfileStatus` enum.

10. **Toolchain keys are plain strings in constants and parser help;** duplicated aliases increase drift. Evidence: [src/neuralspotx/constants.py L20](src/neuralspotx/constants.py#L20). Suggested: `Toolchain` enum with alias parser map.

---

## API Cleanliness Issues

1. **CLI/API inconsistency:** some commands go through API, some directly call `operations`. Evidence: [src/neuralspotx/cli.py L340](src/neuralspotx/cli.py#L340), [L355](src/neuralspotx/cli.py#L355), [L620](src/neuralspotx/cli.py#L620).
2. **API still wraps `SystemExit` as `NSXError`,** indicating domain exceptions are not first-class internally. Evidence: [src/neuralspotx/api.py L214](src/neuralspotx/api.py#L214).
3. **`operations` contains compatibility alias shims** that expose legacy seams and duplicate naming. Evidence: [src/neuralspotx/operations.py L102](src/neuralspotx/operations.py#L102).
4. **Mixed naming styles across module APIs:** `add_module/remove_module/update_modules` vs `lock_app/sync_app/update_app`.
5. **Package root exports CLI `main` alongside library API,** coupling runtime concerns. Evidence: [src/neuralspotx/__init__.py L37](src/neuralspotx/__init__.py#L37).
6. **Public return types for module listing/search/describe are `Any`-heavy dicts,** making programmatic consumers fragile. Evidence: [src/neuralspotx/api.py L683](src/neuralspotx/api.py#L683), [L714](src/neuralspotx/api.py#L714).

---

## Testing Gaps

1. **No direct test for malformed/non-mapping `nsx.yml`** crashing `_load_app_cfg`. Evidence: [tests/test_discovery.py L1](tests/test_discovery.py#L1), [src/neuralspotx/project_config.py L109](src/neuralspotx/project_config.py#L109).
2. **No test proving vendored modules survive `_update_nsx_cfg_modules` rewrites** under remove/update scenarios. Evidence: [src/neuralspotx/module_registry.py L686](src/neuralspotx/module_registry.py#L686), [tests/test_nsx_lock.py L1](tests/test_nsx_lock.py#L1).
3. **No concurrency tests for resolve-ref cache and artifact-hash cache lost updates.** Evidence: [tests/test_resolve_cache.py L1](tests/test_resolve_cache.py#L1), [tests/test_module_cache.py L1](tests/test_module_cache.py#L1).
4. **No coverage for API `lock_app` per-call TTL env override race** with concurrent calls. Evidence: [src/neuralspotx/api.py L762](src/neuralspotx/api.py#L762).
5. **CLI parity tests** do not cover that `view`/`outdated`/`module` commands bypass API timeout normalization. Evidence: [tests/test_public_api_surface.py L1](tests/test_public_api_surface.py#L1), [src/neuralspotx/cli.py L388](src/neuralspotx/cli.py#L388).
6. **No tests for doctor false-positive `CalledProcessError` branch.** Evidence: [src/neuralspotx/operations.py L449](src/neuralspotx/operations.py#L449).
7. **No resilience tests for `extract_view_command`** against varied Ninja formatting. Evidence: [src/neuralspotx/subprocess_utils.py L319](src/neuralspotx/subprocess_utils.py#L319).

---

## Docs vs Reality

1. **Stated architecture:** CLI should be thin and delegate, but real implementation has significant direct `operations` coupling. Evidence: [AGENTS.md L62](AGENTS.md#L62), [src/neuralspotx/cli.py L340](src/neuralspotx/cli.py#L340), [L620](src/neuralspotx/cli.py#L620).
2. **Stated typed-internal-model preference** is only partially realized; many core flows still consume nested dict structures and stringly keys. Evidence: [AGENTS.md L84](AGENTS.md#L84), [src/neuralspotx/project_config.py L28](src/neuralspotx/project_config.py#L28), [src/neuralspotx/module_discovery.py L283](src/neuralspotx/module_discovery.py#L283).
3. **README app-first / pipx-facing intent largely matches code behavior** (create app, configure/build/flash/view, app-local modules). Evidence: [README.md L42](README.md#L42), [src/neuralspotx/operations.py L114](src/neuralspotx/operations.py#L114), [src/neuralspotx/templates/external_app/README.md.j2 L1](src/neuralspotx/templates/external_app/README.md.j2#L1).

---

## Remediation Checklist

Items are sequenced so each builds on previous work. Check off as completed.

- [x] **R1. YAML root validation.** Enforce mapping root in `_read_yaml`/`_load_app_cfg`; emit deterministic `NSXConfigError` for empty/list/scalar/malformed files. *(PR #30–33)*
- [x] **R2. Vendored module preservation.** Fix `_update_nsx_cfg_modules` to preserve vendored entries through remove/update rewrites; add targeted tests. *(PR #30)*
- [x] **R3. TTL env mutation → contextvar.** Replace `os.environ` mutation for per-call resolve TTL with `contextvars.ContextVar`-based `ttl_override()`. *(PR #30)*
- [x] **R4. Fail-closed app lock.** `app_lock` raises `AppLockUnavailableError` on lock-primitive errors by default; opt-out only via `NSX_LOCK_FAIL_OPEN=1`. *(PR #30)*
- [x] **R5. Doctor error classification.** `CalledProcessError` branch reports FAIL unless explicit success criteria met. *(PR #30)*
- [x] **R6. CLI→API routing.** Route all CLI mutating commands through API wrappers so they share timeout/error policy. *(PR #30)*
- [x] **R7. Enums for stringly-typed constants.** `Toolchain`, `Scope`, `ModuleType`, `OutdatedStatus`, `ProfileStatus` enums with `str`-mixin backward compat. *(PR #32–34)*
- [x] **R8. Timeout support for `outdated`/`view`.** `AppOutdatedRequest.timeout_s` and `AppViewRequest.timeout_s` plumbed through API and CLI `--timeout`. *(PR #35)*
- [x] **R9. Structured error hierarchy.** `NSXError(RuntimeError)` + typed subclasses (`NSXConfigError`, `NSXLockError`, etc.) in `_errors.py`; all `raise SystemExit` sites migrated; `_classify`/`_invoke` plumbing deleted; CLI `main()` catches `NSXError` at boundary. *(PR #30–37, M1–M6)*
- [x] **R10. Lock-integrity CI stability.** `nsx-tooling` hash symmetric exclusion of autogen files (`modules.cmake`). *(PR #36)*
- [x] **R11. Cache concurrency hardening.** ~~Resolve-cache and artifact-hash-cache use read-modify-write without inter-process coordination.~~ Both caches now use `file_mutex` for serialized RMW with atomic `os.replace` fallback. *(a94c877)*
- [x] **R12. Operation-scope metadata caching.** ~~Module discovery/search re-deserializes metadata for entire registries on every call.~~ `metadata_cache_scope()` (ContextVar-based) wraps `_resolve_module_closure`, `_module_dependents`, and `_module_discovery_records`. *(a94c877)*
- [x] **R13. Typed domain objects for config/registry.** ~~Replace `dict[str, Any]` spread with `AppConfig`, `ModuleSource`, `ModuleRegistryOverride` dataclasses.~~ `AppConfig`, `AppModule`, `ModuleSource`, `ModuleRegistryOverride` frozen dataclasses in `models.py`; 11 call sites in `project_config.py` and `module_registry.py` converted. *(PR #39)*
- [x] **R14. `LockKind` enum.** ~~Replace stringly-typed `kind: str` on `ResolvedModule` with a proper enum.~~ `ResolvedModule.kind` now typed as `LockKind`; all construction sites and comparisons in `operations.py` use enum members. *(PR #38)*
- [x] **R15. Typed module discovery/search records.** ~~Replace dict blobs returned by `list_modules`/`search_modules`/`describe_module` with `ModuleRecord`/`SearchMatch` dataclasses.~~ `DiscoveryRecord`, `SearchMatch`, `SearchResult` frozen dataclasses in `models.py`; `module_registry`, `module_discovery`, `cli`, `api` all use typed objects; JSON serialization via `.to_dict()` at CLI boundary. *(PR #40)*
- [x] **R16. Typed CLI command descriptors.** ~~Split command graph metadata out of nested dicts into `CommandHint` dataclass + `CommandCategory`/`CommandScope` enums.~~ `CommandHint` frozen dataclass, `CommandCategory`/`CommandScope` str enums in `models.py`; `_COMMAND_GRAPH_HINTS` table and consumers in `cli.py` converted. *(PR #41)*
- [ ] **R17. Board/toolchain/provider single source of truth.** Consolidate Python constants and CMake conditionals into one authoritative mapping (generated or shared). Refs: `constants.py`, `nsx_sdk_providers.cmake`, `nsx_toolchain_flags.cmake`.
- [x] **R18. CLI/API parity tests.** ~~Verify all CLI commands route through API and share timeout/error normalization.~~ 15 parity tests + 2 gap-documenting tests for `cmd_module_list`/`cmd_module_validate` API bypass. *(PR #42)*
- [x] **R19. Cache concurrency tests.** Add inter-process and threaded tests for resolve-cache and artifact-hash-cache under concurrent writers. Refs: `test_resolve_cache.py`, `test_module_cache.py`.
- [ ] **R20. `extract_view_command` resilience tests.** Cover varied Ninja generator formatting to prevent regressions on short-scan-window parsing. Ref: `subprocess_utils.py:319`.
- [ ] **R21. Compatibility alias cleanup in `operations`.** Remove legacy shim aliases that duplicate naming and expose internal seams. Ref: `operations.py:102`.
- [ ] **R22. Decouple `main` from package root exports.** Stop re-exporting CLI `main` from `neuralspotx.__init__` to separate library and runtime concerns. Ref: `__init__.py:37`.
- [ ] **R23. Prefetch error visibility.** Narrow `except Exception` in parallel prefetch to specific expected failures; log root cause instead of silently retrying serially. Ref: `operations.py:1243`.
- [ ] **R24. `create_app` rollback on failure.** Add cleanup/recovery marker so interrupted bootstrap doesn't leave half-generated app state. Ref: `operations.py:192`.
- [ ] **R25. Decompose `operations.py` into `operations/` package.** The 2215-line monolith mixes four distinct concern clusters. Convert to an `operations/` package with sub-modules; `__init__.py` re-exports all public names for full backward compatibility (`from neuralspotx import operations` / `operations.lock_app_impl(...)` unchanged).

  **Proposed sub-modules** (dependency DAG — no cycles):

  | Sub-module | Contents | ~Lines | Internal deps |
  |------------|----------|--------|---------------|
  | `_common.py` | `VERBOSE`, `set_verbosity()`, compat aliases (R21), `OutdatedStatus`, `ProfileStatus` | 60 | — |
  | `_app_lifecycle.py` | `create_app_impl`, `init_module_impl`, `_module_package_name`, `_module_target_name` | 210 | `_common` |
  | `_doctor.py` | `doctor_impl` | 175 | `_common` |
  | `_build.py` | `configure/build/flash/view/clean_app_impl`, `_resolve_build_context`, `_ensure_app_modules`, `_scaffold_vendored_module` | 270 | `_common`, `_sync` |
  | `_modules.py` | `add/remove/update/register_module_impl` | 360 | `_common`, `_lock` |
  | `_lock.py` | `_resolved_module_path`, `_build_lock_for_app`, `lock_app_impl`, `_lock_app_impl_unlocked`, `_diff_locks` | 540 | `_common` |
  | `_sync.py` | `sync_app_impl`, `_sync_app_impl_unlocked`, `outdated_app_impl`, `update_app_impl` | 430 | `_common`, `_lock` |

  **Dependency DAG:**
  ```
  _common  ← (everything)
  _lock    ← _build, _modules, _sync
  _sync    ← _build
  ```

  **Phasing:** Can be done in a single PR (pure mechanical move + `__init__.py` re-export shim). No behavioral changes. R21 (alias cleanup) and R23 (prefetch error narrowing) become scoped to their new sub-modules and can land before or after.
