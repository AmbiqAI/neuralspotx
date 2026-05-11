"""Helpers for reading and writing the ``modules`` list inside an ``nsx.yml``."""

from __future__ import annotations

from typing import Any

from ..models import AppConfig
from ..project_config import _unique_preserving_order
from ._profile import _module_record


def _module_names_from_nsx(nsx_cfg: dict[str, Any]) -> list[str]:
    return AppConfig.from_mapping(nsx_cfg).module_names()


def _is_local_module(nsx_cfg: dict[str, Any], module_name: str) -> bool:
    """Return True if *module_name* is marked ``local: true`` in nsx.yml.

    Local modules live inside the app tree (typically ``modules/<name>/``),
    are source-controlled with the app, and are NOT acquired from a registry
    or git remote.
    """
    return module_name in AppConfig.from_mapping(nsx_cfg).local_module_names()


def _local_module_names(nsx_cfg: dict[str, Any]) -> set[str]:
    """Return the set of modules linked to a local path on disk.

    Keyed off the ``local: true`` flag on the module entry. Note that
    ``_load_app_cfg()`` invokes ``_normalize_module_source()`` first, which
    expands the user-facing ``source: { path: <p> }`` shorthand into
    ``local: true`` plus a ``module_registry.modules.<name>.local_path``
    override -- so both spellings are picked up here.
    """
    return AppConfig.from_mapping(nsx_cfg).local_module_names()


def _vendored_module_names(nsx_cfg: dict[str, Any]) -> set[str]:
    """Return the set of modules declared as ``source: { vendored: true }``.

    Vendored modules live inside the app tree (``modules/<name>/``), are
    source-controlled with the app, and are NEVER touched by ``nsx sync``
    — useful for AOT-generated modules and custom third-party drops.
    """
    return AppConfig.from_mapping(nsx_cfg).vendored_module_names()


def _update_nsx_cfg_modules(
    nsx_cfg: dict[str, Any],
    module_names: list[str],
    registry: dict[str, Any],
) -> None:
    # Preserve existing opaque module entries — they don't come from
    # the registry and must keep their identifying flags:
    #   * ``local: true``                  (path-linked external dir)
    #   * ``source: { vendored: true }``   (committed inside the app tree)
    # Without this, ``add``/``remove``/``update`` rewrites could drop
    # the ``local`` flag or fail when the module isn't in the registry.
    existing_opaque = AppConfig.from_mapping(nsx_cfg).opaque_modules()

    new_modules: list[dict[str, Any]] = []
    for name in _unique_preserving_order(module_names):
        if name in existing_opaque:
            new_modules.append(existing_opaque[name].to_mapping())
        else:
            new_modules.append(_module_record(name, registry))
    nsx_cfg["modules"] = new_modules
