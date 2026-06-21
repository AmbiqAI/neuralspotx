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


def _requires_records(
    requires: list[Any],
    registry: dict[str, Any],
    *,
    seeded_names: set[str],
    module_overrides: dict[str, Any],
) -> list[dict[str, str]]:
    """Resolve additive ``requires`` entries into module records.

    Entries already present in the profile seed (``seeded_names``) are
    skipped so ``requires`` is purely additive. Resolution order per entry:
    an explicit ``project`` pins it; otherwise the board family's
    ``module_overrides`` catalog (every ``sdk_modules`` entry, with its
    ``metadata`` path) is consulted; otherwise the top-level registry
    ``modules`` map. An unknown module raises so typos fail fast.
    """

    records: list[dict[str, str]] = []
    for entry in requires:
        if isinstance(entry, str):
            name, project, revision = entry, None, None
        elif isinstance(entry, dict):
            name = entry.get("name")
            project = entry.get("project")
            revision = entry.get("revision")
        else:
            raise NSXConfigError(
                f"nsx.yml: 'requires' entries must be a module name or mapping, "
                f"got {type(entry).__name__}"
            )
        if not isinstance(name, str) or not name:
            raise NSXConfigError("nsx.yml: 'requires' entry missing a module name")
        if name in seeded_names:
            continue

        if isinstance(project, str) and project:
            overrides: dict[str, Any] | None = {
                name: {"project": project, "revision": revision or ""}
            }
        elif name in module_overrides:
            overrides = module_overrides
        elif name in registry.get("modules", {}):
            overrides = None
        else:
            raise NSXConfigError(
                f"nsx.yml: 'requires' module '{name}' is not in the board's module "
                "catalog or the registry. Check the spelling, or add an explicit "
                "'project' (with a matching 'module_registry' entry)."
            )
        records.append(_module_record(name, registry, overrides))
        seeded_names.add(name)
    return records


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

    An additive ``requires:`` list layers app-specific modules on top of the
    board profile (e.g. USB or timer modules). It is mutually exclusive with
    an authoritative inlined ``modules:`` list.
    """

    requires = nsx_cfg.get("requires") or []
    if "modules" in nsx_cfg:
        if requires:
            raise NSXConfigError(
                "nsx.yml: 'modules' (authoritative closure) and 'requires' (additive "
                "extras layered on the board profile) are mutually exclusive; remove one."
            )
        return nsx_cfg
    target = nsx_cfg.get("target")
    board = target.get("board") if isinstance(target, dict) else None
    if not isinstance(board, str) or not board:
        return nsx_cfg

    modules, module_registry, profile = _profile_seed_blocks(registry, board)
    if requires:
        if not isinstance(requires, list):
            raise NSXConfigError("nsx.yml: 'requires' must be a list")
        seeded_names = {record["name"] for record in modules}
        module_overrides = profile.get("module_overrides", {})
        if not isinstance(module_overrides, dict):
            module_overrides = {}
        modules = modules + _requires_records(
            requires,
            registry,
            seeded_names=seeded_names,
            module_overrides=module_overrides,
        )
    expanded = dict(nsx_cfg)
    expanded["modules"] = modules
    authored = expanded.get("module_registry")
    if not authored:
        expanded["module_registry"] = module_registry
    else:
        # Merge the profile seed *under* the authored registry so an app that
        # authors a partial ``module_registry`` (e.g. only a custom project)
        # but pulls a board-family catalog module via ``requires`` still has
        # that module's override available to ``_effective_registry``. Authored
        # entries win; the seed only fills gaps — mirroring how a fully-inlined
        # manifest already carries the complete profile registry.
        expanded["module_registry"] = _merge_seed_registry(authored, module_registry)
    return expanded


def _merge_seed_registry(
    authored: dict[str, Any],
    seed: dict[str, Any],
) -> dict[str, Any]:
    """Overlay *authored* registry overrides on the profile *seed* registry.

    The seed provides defaults (every profile project/module override);
    authored entries take precedence, merged per-entry so an authored module
    can override a single field (e.g. ``revision``) without dropping the
    seed's ``metadata`` path.
    """

    merged: dict[str, Any] = {
        "projects": copy.deepcopy(seed.get("projects", {})),
        "modules": copy.deepcopy(seed.get("modules", {})),
    }
    for key in ("projects", "modules"):
        authored_section = authored.get(key) if isinstance(authored, dict) else None
        if not isinstance(authored_section, dict):
            continue
        section = merged[key]
        for name, value in authored_section.items():
            existing = section.get(name)
            if isinstance(existing, dict) and isinstance(value, dict):
                combined = dict(existing)
                combined.update(value)
                section[name] = combined
            else:
                section[name] = value
    return merged


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
