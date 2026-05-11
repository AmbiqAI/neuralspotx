"""Helpers for module metadata resolution, dependency closure, and git-based management."""

from __future__ import annotations

from .. import module_cache
from ..project_config import _is_packaged_module
from ._closure import (
    _module_dependents,
    _resolve_module_closure,
    _resolve_module_closure_inner,
)
from ._discovery import _module_discovery_record, _module_discovery_records
from ._metadata import (
    _load_module_metadata,
    _module_metadata_path,
    metadata_cache_scope,
    packaged_module_metadata_path,
    packaged_module_source_dir,
)
from ._nsx_cfg import (
    _is_local_module,
    _local_module_names,
    _module_names_from_nsx,
    _update_nsx_cfg_modules,
    _vendored_module_names,
)
from ._policy import _validate_board_module_dep_policy, _validate_sdk_provider_policy
from ._profile import (
    _generate_nsx_config,
    _module_record,
    _resolve_profile,
    _starter_profile_name,
)
from ._rmtree import _rmtree
from ._table import _print_module_table
from ._vendoring import (
    _acquire_modules_for_app,
    _ensure_module_cloned,
    _remove_vendored_module_from_app,
    _update_module_clone,
    _vendor_git_module_at_commit,
    _vendor_local_module_into_app,
    _vendor_packaged_module_into_app,
)

__all__ = [
    "_acquire_modules_for_app",
    "_ensure_module_cloned",
    "_generate_nsx_config",
    "_is_local_module",
    "_is_packaged_module",
    "_load_module_metadata",
    "_local_module_names",
    "_module_dependents",
    "_module_discovery_record",
    "_module_discovery_records",
    "_module_metadata_path",
    "_module_names_from_nsx",
    "_module_record",
    "_print_module_table",
    "_remove_vendored_module_from_app",
    "_resolve_module_closure",
    "_resolve_module_closure_inner",
    "_resolve_profile",
    "_rmtree",
    "_starter_profile_name",
    "_update_module_clone",
    "_update_nsx_cfg_modules",
    "_validate_board_module_dep_policy",
    "_validate_sdk_provider_policy",
    "_vendor_git_module_at_commit",
    "_vendor_local_module_into_app",
    "_vendor_packaged_module_into_app",
    "_vendored_module_names",
    "metadata_cache_scope",
    "module_cache",
    "packaged_module_metadata_path",
    "packaged_module_source_dir",
]
