"""Starter-profile resolution and initial ``nsx.yml`` generation."""

from __future__ import annotations

import copy
from typing import Any

from .._errors import NSXConfigError
from ..metadata import registry_entry_for_module


def _starter_profile_name(board: str) -> str:
    return f"{board}_minimal"


def _resolve_profile(registry: dict[str, Any], board: str) -> dict[str, Any]:
    name = _starter_profile_name(board)
    profiles = registry["starter_profiles"]
    if name not in profiles:
        raise NSXConfigError(
            f"No starter profile for board '{board}' in registry.lock (expected profile '{name}')."
        )
    profile = profiles[name]
    if not isinstance(profile, dict):
        raise NSXConfigError(f"Invalid profile entry '{name}' in registry.lock")
    return profile


def _module_record(
    module_name: str,
    registry: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, str]:
    # A profile-level module override (e.g. a module sourced from a consolidated
    # SDK monorepo) must win over the base registry's tier-agnostic default so
    # the generated ``modules:`` pin agrees with ``module_registry.modules`` and
    # passes the partial-migration alignment guard.
    override = (overrides or {}).get(module_name)
    if isinstance(override, dict) and "project" in override:
        return {
            "name": module_name,
            "revision": override.get("revision", ""),
            "project": override["project"],
        }
    entry = registry_entry_for_module(registry, module_name)
    return {
        "name": module_name,
        "revision": entry.revision,
        "project": entry.project,
    }


def _profile_seed_blocks(
    registry: dict[str, Any],
    board: str,
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    """Derive the inlined ``modules`` + ``module_registry`` seed blocks for *board*.

    Shared by app creation (:func:`_generate_nsx_config`) and profile-seeded
    resolution (:func:`expand_profile_seeds`) so a lean manifest expands to a
    closure that is byte-compatible with the one a freshly-scaffolded app
    would inline. Returns ``(modules, module_registry, profile)``.
    """

    profile = _resolve_profile(registry, board)
    profile_modules = profile.get("modules", [])
    if not isinstance(profile_modules, list):
        raise NSXConfigError(f"Invalid modules list in profile for board '{board}'")
    profile_project_overrides = profile.get("project_overrides", {})
    if not isinstance(profile_project_overrides, dict):
        raise NSXConfigError(f"Invalid project_overrides mapping in profile for board '{board}'")
    profile_module_overrides = profile.get("module_overrides", {})
    if not isinstance(profile_module_overrides, dict):
        raise NSXConfigError(f"Invalid module_overrides mapping in profile for board '{board}'")

    modules = [_module_record(name, registry, profile_module_overrides) for name in profile_modules]
    module_registry = {
        "projects": copy.deepcopy(profile_project_overrides),
        "modules": copy.deepcopy(profile_module_overrides),
    }
    return modules, module_registry, profile


def expand_profile_seeds(
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Seed ``modules``/``module_registry`` from the app's profile when absent.

    Lean manifests omit the resolved module closure and registry overrides;
    this rebuilds them in-memory from the app's starter profile (the same
    derivation used at app creation) so the resolver sees an equivalent
    fully-seeded config. A manifest that already declares ``modules`` (even
    an explicitly empty ``modules: []``, e.g. ``--no-bootstrap``) is
    returned unchanged, and any explicitly-authored ``module_registry`` is
    preserved.
    """

    if "modules" in nsx_cfg:
        return nsx_cfg
    target = nsx_cfg.get("target")
    board = target.get("board") if isinstance(target, dict) else None
    if not isinstance(board, str) or not board:
        return nsx_cfg

    modules, module_registry, _profile = _profile_seed_blocks(registry, board)
    expanded = dict(nsx_cfg)
    expanded["modules"] = modules
    if not expanded.get("module_registry"):
        expanded["module_registry"] = module_registry
    return expanded


def _generate_nsx_config(
    app_name: str,
    board: str,
    soc: str,
    registry: dict[str, Any],
    *,
    default_toolchain: str,
    nsx_version: str | None,
    nsx_major: int | None,
) -> dict[str, Any]:
    modules, module_registry, profile = _profile_seed_blocks(registry, board)

    return {
        "schema_version": 1,
        "project": {"name": app_name},
        "target": {"board": board, "soc": soc},
        "toolchain": profile.get("toolchain", default_toolchain),
        "channel": profile.get("channel", "stable"),
        "profile": _starter_profile_name(board),
        "profile_status": profile.get("status", "active"),
        "modules": modules,
        "features": profile.get("features", {}),
        "tooling": {
            "nsx": {
                "version": nsx_version,
                "major": nsx_major,
            }
        },
        "module_registry": module_registry,
    }
