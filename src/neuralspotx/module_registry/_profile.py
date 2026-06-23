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


def _direct_dep_records(
    direct: tuple[Any, ...],
    registry: dict[str, Any],
    *,
    seeded_names: set[str],
    module_overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve the app's direct ``modules:`` deps into closure records.

    Each entry is an :class:`~neuralspotx.models.AppModule`. Entries already
    present in the profile seed (``seeded_names``) are skipped so the direct
    list is purely additive on the board profile. Resolution by source kind:

    * **registry** -- an explicit ``project`` pins it; otherwise the board
      family's ``module_overrides`` catalog is consulted; otherwise the
      top-level registry ``modules`` map. An unknown module raises so typos
      fail fast.
    * **path** / **vendored** -- opaque; the user entry's identifying flags
      (``local`` / ``source.vendored``) are preserved verbatim so the
      lock/sync layer treats them as in-tree sources.
    * **git** -- not yet wired into resolution; raises a clear error.
    """

    records: list[dict[str, Any]] = []
    for module in direct:
        name = module.name
        if not isinstance(name, str) or not name:
            raise NSXConfigError("nsx.yml: 'modules' entry missing a module name")
        if name in seeded_names:
            continue

        kind = module.source_kind
        if kind == "git":
            raise NSXConfigError(
                f"nsx.yml: module '{name}' uses a git source, which is not yet "
                "supported by the resolver. Use a registry, path, or vendored "
                "source for now."
            )
        if kind in ("path", "vendored"):
            # Opaque in-tree source: keep the user entry's flags as-is.
            records.append(_opaque_record(module))
            seeded_names.add(name)
            continue

        project = module.project
        revision = module.revision
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
                f"nsx.yml: module '{name}' is not in the board's module catalog "
                "or the registry. Check the spelling, or add an explicit 'project' "
                "(with a matching 'module_registry' entry)."
            )
        records.append(_module_record(name, registry, overrides))
        seeded_names.add(name)
    return records


def _opaque_record(module: Any) -> dict[str, Any]:
    """Closure record for an opaque (path/vendored) direct dependency.

    Emits only the identifying fields the lock/sync layer reads
    (``name`` + ``local`` / ``source.vendored``); the per-entry ``boards``
    filter has already been applied upstream and is dropped here.
    """

    record: dict[str, Any] = {"name": module.name}
    if module.is_local:
        record["local"] = True
    if module.is_vendored:
        record["source"] = {"vendored": True}
    return record


def expand_profile_seeds(
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the app's closure from its board profile + direct ``modules:``.

    Schema v2 treats ``modules:`` as the app's *direct* dependencies, layered
    additively on the board's starter profile (the implicit baseline). This
    rebuilds the full module closure in-memory:

    * Seed every module from the board's starter profile (the same derivation
      used at app creation), then layer the app's direct ``modules:`` deps on
      top, skipping any already present in the seed.
    * ``baseline: none`` opts out of profile seeding entirely, making the
      direct ``modules:`` list the authoritative closure (an empty list yields
      an empty closure — the bare-metal / ``--no-bootstrap`` case).

    The active board is read from ``target.board`` (already pinned by
    :func:`_apply_active_target` for multi-target apps), and each direct dep's
    per-entry ``boards`` filter scopes it to the active board. Any authored
    ``module_registry`` block is preserved (authored entries win; the profile
    seed only fills gaps).
    """

    from ..models import AppConfig

    app = AppConfig.from_mapping(nsx_cfg)
    target = nsx_cfg.get("target")
    board = target.get("board") if isinstance(target, dict) else None
    board = board if isinstance(board, str) and board else None

    direct = app.direct_modules(board)

    # Modules registered into the app's own ``module_registry`` (e.g. a local
    # project added via ``nsx module register``) map a bare ``modules:`` name to
    # an explicit project. Surface those as overrides so a lean ``{name: ...}``
    # direct dep still resolves without re-inlining the project on each entry.
    authored_registry = nsx_cfg.get("module_registry")
    app_module_overrides = (
        authored_registry.get("modules", {})
        if isinstance(authored_registry, dict)
        else {}
    )
    if not isinstance(app_module_overrides, dict):
        app_module_overrides = {}

    if app.baseline_disabled:
        # Authoritative: the direct list is the whole closure, no profile seed.
        seeded_names: set[str] = set()
        modules = _direct_dep_records(
            direct, registry, seeded_names=seeded_names, module_overrides=app_module_overrides
        )
        expanded = dict(nsx_cfg)
        expanded["modules"] = modules
        return expanded

    if board is None:
        # No board to seed from (edge/legacy manifest); leave untouched.
        return nsx_cfg

    seed_modules, module_registry, profile = _profile_seed_blocks(registry, board)
    seeded_names = {record["name"] for record in seed_modules}
    module_overrides = profile.get("module_overrides", {})
    if not isinstance(module_overrides, dict):
        module_overrides = {}
    # Authored app overrides win over the board-family catalog.
    module_overrides = {**module_overrides, **app_module_overrides}

    modules = seed_modules + _direct_dep_records(
        direct,
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
        # but pulls a board-family catalog module via a direct dep still has
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
        "schema_version": 2,
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
