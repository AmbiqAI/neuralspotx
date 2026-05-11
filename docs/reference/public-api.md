# Public Python API

This page is the **canonical inventory** of the `neuralspotx` Python
public surface. Every name listed here is importable as
`from neuralspotx import <Name>` and is covered by the version-stability
contract for that tier.

`tests/test_public_surface_doc.py` keeps `neuralspotx.__all__` and this
document in sync — if you add or remove a name from `__all__`, update
the matching table here (and vice versa) or CI will fail.

## Stability tiers

- **Stable** — frozen at v1.0. Removal or signature-breaking change
  requires a major version bump.
- **Provisional** — public, but may change before v1.0 ships. Pin an
  exact NSX version if you depend on these.

The current tier of every symbol below is **Provisional** until v1.0 is
tagged; this page will be updated at the v1.0 release.

## Errors

| Symbol | Kind | Tier |
|---|---|---|
| `NSXError` | exception base | Provisional |
| `NSXConfigError` | exception | Provisional |
| `NSXLockError` | exception | Provisional |
| `NSXModuleError` | exception | Provisional |
| `NSXResolutionError` | exception | Provisional |
| `NSXTimeoutError` | exception | Provisional |
| `NSXToolchainError` | exception | Provisional |

## API callables

| Symbol | Returns | Tier |
|---|---|---|
| `create_app` | `Path` | Provisional |
| `configure_app` | `None` | Provisional |
| `build_app` | `None` | Provisional |
| `flash_app` | `None` | Provisional |
| `view_app` | `None` | Provisional |
| `clean_app` | `None` | Provisional |
| `doctor` | `DoctorReport` | Provisional |
| `lock_app` | `NsxLock` | Provisional |
| `sync_app` | `None` | Provisional |
| `outdated_app` | `OutdatedReport` | Provisional |
| `update_app` | `None` | Provisional |
| `add_module` | `list[ModuleChange]` | Provisional |
| `remove_module` | `list[ModuleChange]` | Provisional |
| `update_modules` | `list[ModuleChange]` | Provisional |
| `register_module` | `ModuleChange` | Provisional |
| `init_module` | `ModuleChange` | Provisional |
| `list_modules` | `list[DiscoveryRecord]` | Provisional |
| `describe_module` | `DiscoveryRecord` | Provisional |
| `search_modules` | `list[SearchResult]` | Provisional |
| `validate_module_metadata` | `dict` | Provisional |
| `cache_info` | `CacheInfo` | Provisional |
| `clean_cache` | `CacheCleanResult` | Provisional |
| `find_app_root` | `Path \| None` | Provisional |
| `resolve_app_dir` | `Path` | Provisional |

## Request dataclasses

Each `*Request` dataclass is the typed input to the matching API
callable. Construction with positional/keyword arguments is part of the
contract; dataclass field names are part of the contract.

| Symbol | Used by | Tier |
|---|---|---|
| `AppCreateRequest` | `create_app` | Provisional |
| `AppActionRequest` | base class for app-scoped actions | Provisional |
| `AppViewRequest` | `view_app` | Provisional |
| `AppBuildRequest` | `build_app` | Provisional |
| `AppFlashRequest` | `flash_app` | Provisional |
| `AppCleanRequest` | `clean_app` | Provisional |
| `AppLockRequest` | `lock_app` | Provisional |
| `AppSyncRequest` | `sync_app` | Provisional |
| `AppOutdatedRequest` | `outdated_app` | Provisional |
| `AppUpdateRequest` | `update_app` | Provisional |
| `ModuleChangeRequest` | `add_module` / `remove_module` | Provisional |
| `ModuleUpdateRequest` | `update_modules` | Provisional |
| `ModuleRegisterRequest` | `register_module` | Provisional |
| `ModuleInitRequest` | `init_module` | Provisional |

## Result / data models

| Symbol | Returned by | Tier |
|---|---|---|
| `DoctorReport`, `DoctorCheck` | `doctor` | Provisional |
| `OutdatedReport`, `OutdatedModule`, `OutdatedSkip` | `outdated_app` | Provisional |
| `ModuleChange` | module mutation API | Provisional |
| `CacheInfo`, `CacheEntry`, `CacheCleanResult` | `cache_info` / `clean_cache` | Provisional |
| `DiscoveryRecord` | `list_modules` / `describe_module` | Provisional |
| `SearchResult`, `SearchMatch` | `search_modules` | Provisional |
| `CommandHint`, `CommandCategory`, `CommandScope` | introspection (`nsx commands`) | Provisional |

## Lock model + enums

| Symbol | Source | Tier |
|---|---|---|
| `NsxLock` | parsed `nsx.lock` | Provisional |
| `ResolvedModule` | one entry within `NsxLock.modules` | Provisional |
| `LockKind` | `git \| local \| vendored` | Provisional |
| `OutdatedStatus` | `current \| outdated \| unknown` | Provisional |
| `ProfileStatus` | doctor profile probe outcome | Provisional |

## Internal modules (NOT public)

The following modules are implementation details and may change without
notice. Do not import from them directly:

- `neuralspotx.cli` — argparse-based command implementation
- `neuralspotx.operations.*` — `*_impl` workhorses (use `neuralspotx.api` instead)
- `neuralspotx.module_registry`, `neuralspotx.module_discovery`,
  `neuralspotx.module_cache`
- `neuralspotx.project_config`
- `neuralspotx.subprocess_utils`, `neuralspotx.file_lock`,
  `neuralspotx.tooling`, `neuralspotx.metadata`
- Anything beginning with an underscore (`_logging`, `_resolve_cache`,
  `_errors` re-exports the public exception types but the module path
  itself is internal)
