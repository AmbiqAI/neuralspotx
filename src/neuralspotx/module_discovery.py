"""Module discovery, search, and compatibility helpers.

This module owns the logic that was previously embedded in cli.py for
resolving module context, computing search scores, and checking target
compatibility.  Both the public API and the CLI delegate here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .constants import DEFAULT_TOOLCHAIN
from .metadata import is_compatible
from .module_registry import (
    _module_discovery_record,
    _module_discovery_records,
    _module_names_from_nsx,
)
from .project_config import (
    _effective_registry,
    _load_app_cfg,
    _load_registry,
)


# ------------------------------------------------------------------
# Module context resolution
# ------------------------------------------------------------------


def resolve_module_context(
    *,
    app_dir: Path | None,
) -> tuple[dict, set[str], Path | None, str]:
    """Build the registry / enabled-set pair for module queries.

    Returns ``(registry, enabled_names, resolved_app_dir, scope_label)``.
    *scope_label* is ``"packaged"`` when no app is involved, or
    ``"app-effective"`` when an app's overrides are merged in.
    """

    base_registry = _load_registry()

    if app_dir is None:
        return base_registry, set(), None, "packaged"

    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(base_registry, nsx_cfg)
    enabled = set(_module_names_from_nsx(nsx_cfg))
    return registry, enabled, app_dir, "app-effective"


# ------------------------------------------------------------------
# Target context
# ------------------------------------------------------------------


def resolve_target_context(
    *,
    app_dir: Path | None,
    board: str | None = None,
    soc: str | None = None,
    toolchain: str | None = None,
) -> dict[str, str] | None:
    """Merge explicit filters with the app's target config."""

    if app_dir is not None:
        nsx_cfg = _load_app_cfg(app_dir)
        target = nsx_cfg.get("target", {})
        resolved = {
            "board": board or target.get("board"),
            "soc": soc or target.get("soc"),
            "toolchain": toolchain or nsx_cfg.get("toolchain", DEFAULT_TOOLCHAIN),
        }
    else:
        resolved = {
            "board": board,
            "soc": soc,
            "toolchain": toolchain,
        }

    if all(isinstance(v, str) and v for v in resolved.values()):
        return {k: str(v) for k, v in resolved.items()}
    if any(v is not None for v in resolved.values()):
        return {k: str(v) for k, v in resolved.items() if isinstance(v, str) and v}
    return None


# ------------------------------------------------------------------
# Compatibility
# ------------------------------------------------------------------


def compatibility_matches(
    record: dict, target_context: dict[str, str] | None
) -> bool | None:
    """Check whether *record* is compatible with *target_context*."""

    if not record.get("metadata_available"):
        return None
    if not target_context:
        return None

    if {"board", "soc", "toolchain"}.issubset(target_context):
        return is_compatible(
            {"compatibility": record["compatibility"]},
            board=target_context["board"],
            soc=target_context["soc"],
            toolchain=target_context["toolchain"],
        )

    compat = record["compatibility"]
    for field, current in target_context.items():
        values = compat.get(f"{field}s", [])
        if "*" in values:
            continue
        if current not in values:
            return False
    return True


# ------------------------------------------------------------------
# Search scoring
# ------------------------------------------------------------------


def _search_haystacks(record: dict) -> list[tuple[str, str]]:
    haystacks = [
        ("name", record["name"]),
        ("project", record["project"]),
        ("revision", record["revision"]),
    ]
    if not record.get("metadata_available"):
        return haystacks

    module = record["module"]
    haystacks.extend([
        ("module.name", module["name"]),
        ("module.type", module["type"]),
        ("module.version", module["version"]),
    ])
    for field in ("category", "provider"):
        if field in module:
            haystacks.append((f"module.{field}", module[field]))

    for target in record["build"]["cmake"]["targets"]:
        haystacks.append(("build.target", target))
    for dep in record["depends"]["required"]:
        haystacks.append(("depends.required", dep))
    for dep in record["depends"]["optional"]:
        haystacks.append(("depends.optional", dep))
    for board in record["compatibility"]["boards"]:
        haystacks.append(("compatibility.board", board))
    for soc in record["compatibility"]["socs"]:
        haystacks.append(("compatibility.soc", soc))
    for tc in record["compatibility"]["toolchains"]:
        haystacks.append(("compatibility.toolchain", tc))

    provides = record.get("provides", {})
    if isinstance(provides, dict):
        for key, values in provides.items():
            if isinstance(values, list):
                for v in values:
                    haystacks.append((f"provides.{key}", str(v)))
            else:
                haystacks.append((f"provides.{key}", str(values)))

    for key in ("capabilities", "use_cases", "agent_keywords"):
        vals = record.get(key)
        if isinstance(vals, list):
            for v in vals:
                haystacks.append((key, str(v)))
        elif isinstance(vals, str):
            haystacks.append((key, vals))
    if isinstance(record.get("summary"), str):
        haystacks.append(("summary", record["summary"]))
    return haystacks


def _search_score(record: dict, query: str) -> tuple[int, list[dict[str, str]]]:
    haystacks = _search_haystacks(record)
    nq = query.strip().lower()
    tokens = [t for t in re.split(r"[^a-z0-9_]+", nq) if t]
    if not tokens:
        return 0, []

    score = 0
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for field, value in haystacks:
        nv = value.lower()
        if nq and nq == nv:
            k = (field, nq, value)
            if k not in seen:
                seen.add(k)
                matches.append({"field": field, "term": nq, "value": value})
            score += 12
        elif nq and nq in nv:
            k = (field, nq, value)
            if k not in seen:
                seen.add(k)
                matches.append({"field": field, "term": nq, "value": value})
            score += 6

        for token in tokens:
            if token == nv:
                k = (field, token, value)
                if k not in seen:
                    seen.add(k)
                    matches.append({"field": field, "term": token, "value": value})
                score += 8
            elif token in nv:
                k = (field, token, value)
                if k not in seen:
                    seen.add(k)
                    matches.append({"field": field, "term": token, "value": value})
                score += 3

    return score, matches


# ------------------------------------------------------------------
# Public discovery API
# ------------------------------------------------------------------


def list_modules(
    *,
    app_dir: Path | None = None,
    registry_only: bool = False,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """Return the module catalog as a list of discovery records.

    When *registry_only* is ``True``, the packaged registry is used
    regardless of *app_dir*.
    """

    effective_app = None if registry_only else app_dir
    registry, enabled, resolved_app, _ = resolve_module_context(
        app_dir=effective_app,
    )
    return _module_discovery_records(
        registry,
        enabled,
        app_dir=resolved_app,
        include_metadata=include_metadata,
    )


def describe_module(
    module: str,
    *,
    app_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a single module discovery record.

    Raises ``ValueError`` if the module is not in the registry.
    """

    registry, enabled, resolved_app, _ = resolve_module_context(
        app_dir=app_dir,
    )
    return _module_discovery_record(
        module,
        registry,
        app_dir=resolved_app,
        enabled=module in enabled,
        include_metadata=True,
    )


def search_modules(
    query: str,
    *,
    app_dir: Path | None = None,
    board: str | None = None,
    soc: str | None = None,
    toolchain: str | None = None,
    include_incompatible: bool = False,
) -> list[dict[str, Any]]:
    """Search the module catalog by keyword, capability, or intent.

    Returns a scored, sorted list of matching discovery records.
    """

    registry, enabled, resolved_app, _ = resolve_module_context(
        app_dir=app_dir,
    )
    target_ctx = resolve_target_context(
        app_dir=resolved_app,
        board=board,
        soc=soc,
        toolchain=toolchain,
    )

    results: list[dict[str, Any]] = []
    for record in _module_discovery_records(
        registry, enabled, app_dir=resolved_app, include_metadata=True,
    ):
        score, matches = _search_score(record, query)
        if score <= 0:
            continue
        compat = compatibility_matches(record, target_ctx)
        if compat is False and not include_incompatible:
            continue
        result = dict(record)
        result["score"] = score
        result["matches"] = matches
        result["compatible"] = compat
        results.append(result)

    results.sort(key=lambda r: (r["compatible"] is False, -r["score"], r["name"]))
    return results
