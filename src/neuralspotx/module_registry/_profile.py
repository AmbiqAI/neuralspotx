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


def _module_record(module_name: str, registry: dict[str, Any]) -> dict[str, str]:
    entry = registry_entry_for_module(registry, module_name)
    return {
        "name": module_name,
        "revision": entry.revision,
        "project": entry.project,
    }


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

    return {
        "schema_version": 1,
        "project": {"name": app_name},
        "target": {"board": board, "soc": soc},
        "toolchain": profile.get("toolchain", default_toolchain),
        "channel": profile.get("channel", "stable"),
        "profile": _starter_profile_name(board),
        "profile_status": profile.get("status", "active"),
        "modules": [_module_record(name, registry) for name in profile_modules],
        "features": profile.get("features", {}),
        "tooling": {
            "nsx": {
                "version": nsx_version,
                "major": nsx_major,
            }
        },
        "module_registry": {
            "projects": copy.deepcopy(profile_project_overrides),
            "modules": copy.deepcopy(profile_module_overrides),
        },
    }
