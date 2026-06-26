# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Programmatic API for the NSX workflow.

Stable public surface for embedders. The actual implementations live in
sibling submodules (``_requests``, ``_app``, ``_modules``, ``_lock``,
``_cache``, ``_sbom``); this facade re-exports them so existing
``from neuralspotx.api import …`` imports keep working.
"""

from __future__ import annotations

from pathlib import Path

from .. import operations
from .._errors import NSXConfigError, NSXError, NSXModuleError
from ._app import (
    build_app,
    clean_app,
    configure_app,
    create_app,
    doctor,
    flash_app,
    view_app,
)
from ._board import create_board
from ._cache import cache_info, clean_cache
from ._lock import lock_app, outdated_app, sync_app, update_app
from ._modules import (
    add_module,
    describe_module,
    find_app_root,
    init_module,
    list_modules,
    register_module,
    remove_module,
    resolve_app_dir,
    search_modules,
    update_modules,
    validate_module_metadata,
)
from ._registry import load_registry, registry_module_project, starter_profile
from ._requests import (
    AppActionRequest,
    AppBuildRequest,
    AppCleanRequest,
    AppCreateRequest,
    AppFlashRequest,
    AppLockRequest,
    AppOutdatedRequest,
    AppSyncRequest,
    AppUpdateRequest,
    AppViewRequest,
    BoardCreateRequest,
    ModuleChangeRequest,
    ModuleInitRequest,
    ModuleRegisterRequest,
    ModuleUpdateRequest,
    PathLike,
)
from ._sbom import generate_sbom

__all__ = [
    "AppActionRequest",
    "AppBuildRequest",
    "AppCleanRequest",
    "AppCreateRequest",
    "AppFlashRequest",
    "AppLockRequest",
    "AppOutdatedRequest",
    "AppSyncRequest",
    "AppUpdateRequest",
    "AppViewRequest",
    "BoardCreateRequest",
    "ModuleChangeRequest",
    "ModuleInitRequest",
    "ModuleRegisterRequest",
    "ModuleUpdateRequest",
    "NSXConfigError",
    "NSXError",
    "NSXModuleError",
    "PathLike",
    "add_module",
    "operations",
    "build_app",
    "cache_info",
    "clean_app",
    "clean_cache",
    "configure_app",
    "create_app",
    "create_board",
    "describe_module",
    "doctor",
    "find_app_root",
    "flash_app",
    "generate_sbom",
    "init_module",
    "list_modules",
    "lock_app",
    "load_registry",
    "outdated_app",
    "registry_module_project",
    "register_module",
    "remove_module",
    "resolve_app_dir",
    "search_modules",
    "starter_profile",
    "sync_app",
    "update_app",
    "update_modules",
    "view_app",
]
