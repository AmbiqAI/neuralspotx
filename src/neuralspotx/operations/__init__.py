"""Shared NSX workflow operations for CLI and programmatic use.

The package implements every ``*_impl`` workhorse behind
``neuralspotx.api`` and ``nsx`` (the CLI) in focused sub-modules. The
public surface is re-exported here so existing callers (``api``,
``cli``, tests) can reference ``neuralspotx.operations.<name>``
unchanged.

Sub-module layout
-----------------

* ``_common``         — verbosity context (``set_verbosity``,
                        ``get_verbosity``, ``verbosity``), status
                        enums, name helpers, build-context resolver,
                        vendored-module scaffolder.
* ``_app_lifecycle``  — ``create_app_impl``, ``init_module_impl``.
* ``_doctor``         — ``doctor_impl``.
* ``_lock``           — ``lock_app_impl``, ``outdated_app_impl`` and helpers.
* ``_sync``           — ``sync_app_impl``, ``update_app_impl``,
                        ``_ensure_app_modules``.
* ``_build``          — ``configure_app_impl``, ``build_app_impl``,
                        ``flash_app_impl``, ``view_app_impl``,
                        ``clean_app_impl``.
* ``_modules``        — ``add_module_impl``, ``remove_module_impl``,
                        ``update_modules_impl``, ``register_module_impl``.
* ``_cache``          — ``cache_info_impl``, ``clean_cache_impl``.

Tests that need to monkeypatch helpers imported by a specific sub-module
should target that sub-module directly (e.g. ``operations._lock.resolve_ref``)
rather than the package, since ``from .nsx_lock import resolve_ref`` binds
the name in the importing sub-module's globals.
"""

from __future__ import annotations

# Sub-modules are intentionally exposed as attributes of the package so
# tests can do ``monkeypatch.setattr(operations._lock, "resolve_ref", ...)``.
from . import (  # noqa: F401
    _app_lifecycle,
    _build,
    _cache,
    _common,
    _doctor,
    _lock,
    _modules,
    _sbom,
    _sync,
)
from ._app_lifecycle import create_app_impl, init_module_impl
from ._build import (
    build_app_impl,
    clean_app_impl,
    configure_app_impl,
    flash_app_impl,
    view_app_impl,
)
from ._cache import cache_info_impl, clean_cache_impl
from ._common import OutdatedStatus, ProfileStatus, get_verbosity, set_verbosity, verbosity
from ._doctor import doctor_impl
from ._lock import lock_app_impl, outdated_app_impl
from ._modules import (
    add_module_impl,
    register_module_impl,
    remove_module_impl,
    update_modules_impl,
)
from ._sbom import generate_sbom_impl
from ._sync import sync_app_impl, update_app_impl

__all__ = [
    # Enums
    "OutdatedStatus",
    "ProfileStatus",
    # App lifecycle
    "create_app_impl",
    "init_module_impl",
    # Cache
    "cache_info_impl",
    "clean_cache_impl",
    # Build / configure / flash / view / clean
    "build_app_impl",
    "clean_app_impl",
    "configure_app_impl",
    "flash_app_impl",
    "view_app_impl",
    # Doctor
    "doctor_impl",
    # Lock / outdated
    "lock_app_impl",
    "outdated_app_impl",
    # Sync / update
    "sync_app_impl",
    "update_app_impl",
    # Modules
    "add_module_impl",
    "register_module_impl",
    "remove_module_impl",
    "update_modules_impl",
    # SBOM
    "generate_sbom_impl",
    # Verbosity
    "get_verbosity",
    "set_verbosity",
    "verbosity",
]
