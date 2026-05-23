"""Module metadata resolution and operation-scope caching."""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .._errors import NSXResolutionError
from ..metadata import (
    RegistryModuleEntry,
    registry_entry_for_module,
    validate_nsx_module_metadata,
)
from ..project_config import (
    _metadata_path_relative_to_project,
    _module_clone_dir,
    _packaged_metadata_path,
    _read_yaml,
    _registry_project_entry,
    _vendored_metadata_relpath,
)

# ---------------------------------------------------------------------------
# Operation-scope metadata cache
# ---------------------------------------------------------------------------
#
# ``_load_module_metadata`` parses + validates ``nsx-module.yaml`` from
# disk on every call.  Discovery flows (``list_modules``,
# ``search_modules``, ``describe_module``) and dependency-closure flows
# (``_resolve_module_closure``, ``_module_dependents``) hit it many
# times per command for the same module.  We cache results inside an
# explicit operation scope so:
#
#   * Long-lived processes that embed NSX (helia-profiler, etc.) can't
#     accidentally consume stale on-disk metadata between runs — the
#     cache only exists while a ``with metadata_cache_scope():`` is
#     active.
#   * Concurrent callers don't share a cache (``ContextVar`` is
#     thread/async-task local).
#
# Keyed by ``(module_name, str(app_dir) or "")``; the registry itself
# is captured by the caller's choice to enter the scope, so we don't
# need to key on it.

_metadata_scope: contextvars.ContextVar[dict[tuple[str, str], dict[str, Any]] | None] = (
    contextvars.ContextVar("nsx_metadata_scope", default=None)
)


@contextlib.contextmanager
def metadata_cache_scope() -> Iterator[None]:
    """Enable per-operation memoization of ``_load_module_metadata``.

    Within this with-block, repeated calls to load a given
    ``(module_name, app_dir)`` pair return the cached parse without
    re-reading or re-validating ``nsx-module.yaml``. Nested scopes are
    no-ops (the outermost scope owns the cache).
    """

    if _metadata_scope.get() is not None:
        yield
        return
    token = _metadata_scope.set({})
    try:
        yield
    finally:
        _metadata_scope.reset(token)


def _module_metadata_path(
    module_name: str,
    registry_entry: RegistryModuleEntry,
    registry: dict[str, Any],
    app_dir: Path | None = None,
) -> Path:
    metadata = Path(registry_entry.metadata)

    # 1. Check app-local vendored / cloned path
    if app_dir is not None and not metadata.is_absolute():
        vendored_path = app_dir / _vendored_metadata_relpath(registry_entry.metadata)
        if vendored_path.exists():
            return vendored_path

    if metadata.is_absolute():
        if metadata.exists():
            return metadata
        raise NSXResolutionError(
            f"Unable to locate nsx-module.yaml for module '{module_name}' at "
            f"absolute path '{metadata}'"
        )

    # 2. Check packaged content (boards, cmake shipped with neuralspotx)
    packaged = _packaged_metadata_path(metadata)
    if packaged is not None:
        return packaged

    # 3. Check app-local module clone directory
    if app_dir is not None:
        project_entry = _registry_project_entry(registry, registry_entry.project)
        project_path = project_entry.path
        metadata_rel = _metadata_path_relative_to_project(metadata, project_path)
        clone_dir = _module_clone_dir(app_dir, registry_entry.project, registry)
        candidate = clone_dir / metadata_rel
        if candidate.exists():
            return candidate

    # 4. Check user-registered local path
    project_entry = _registry_project_entry(registry, registry_entry.project)
    if project_entry.local_path:
        local_root = Path(project_entry.local_path).expanduser()
        metadata_rel = _metadata_path_relative_to_project(metadata, project_entry.path)
        candidate = local_root / metadata_rel
        if candidate.exists():
            return candidate

    searched = [str(metadata)]
    if app_dir:
        searched.append(str(_module_clone_dir(app_dir, registry_entry.project, registry)))
    raise NSXResolutionError(
        f"Unable to locate nsx-module.yaml for module '{module_name}'. "
        f"Searched: {', '.join(searched)}"
    )


def _normalize_legacy_registry_metadata(data: dict[str, Any], module_name: str) -> dict[str, Any]:
    """Return a current-schema view for older registry module metadata.

    Some public modules were published before ``build.cmake.package`` and
    ``compatibility`` became required authoring fields. The resolver only needs
    a dependency/compatibility view of metadata, so registry-loaded modules get
    this narrow compatibility shim. Explicit validation commands still call
    ``validate_nsx_module_metadata`` directly and keep enforcing the current
    authoring schema.
    """

    build = data.get("build")
    if isinstance(build, dict):
        cmake = build.get("cmake")
        if isinstance(cmake, dict) and "package" not in cmake:
            targets = cmake.get("targets")
            if isinstance(targets, list) and targets and isinstance(targets[0], str):
                first_target = targets[0].split("::")[-1]
                cmake["package"] = (
                    first_target if first_target.startswith("nsx_") else f"nsx_{first_target}"
                )
            else:
                cmake["package"] = module_name.replace("-", "_")

    if "compatibility" not in data:
        data["compatibility"] = {
            "boards": data.get("boards", ["*"]),
            "socs": data.get("socs", ["*"]),
            "toolchains": data.get("toolchains", ["*"]),
        }

    return data


def _load_module_metadata(
    module_name: str,
    registry: dict[str, Any],
    app_dir: Path | None = None,
) -> dict[str, Any]:
    cache = _metadata_scope.get()
    cache_key: tuple[str, str] | None = None
    if cache is not None:
        cache_key = (module_name, str(app_dir) if app_dir is not None else "")
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    entry = registry_entry_for_module(registry, module_name)
    metadata_path = _module_metadata_path(module_name, entry, registry, app_dir=app_dir)
    data = _read_yaml(metadata_path)
    data = _normalize_legacy_registry_metadata(data, module_name)
    validate_nsx_module_metadata(data, str(metadata_path))

    if cache is not None and cache_key is not None:
        cache[cache_key] = data
    return data


def packaged_module_metadata_path(
    module_name: str,
    registry_entry: RegistryModuleEntry,
    registry: dict[str, Any],
) -> Path:
    """Resolve the ``nsx-module.yaml`` path for a *packaged* module.

    Companion to :func:`packaged_module_source_dir`; always passes
    ``app_dir=None`` so the result is the wheel resource path, not
    an app-local materialized copy.
    """

    return _module_metadata_path(module_name, registry_entry, registry, app_dir=None)


def packaged_module_source_dir(
    module_name: str,
    registry_entry: RegistryModuleEntry,
    registry: dict[str, Any],
) -> Path:
    """Resolve the source directory for a *packaged* module.

    Public API for callers (e.g. ``nsx_lock``) that need the wheel
    resource path without consulting any app-local materialized copy.
    Always passes ``app_dir=None`` so the result is the upstream
    artifact, never an on-disk vendored tree under ``modules/``.

    Returns the directory containing ``nsx-module.yaml`` (i.e. the
    source root); callers that want the metadata file itself can use
    :func:`packaged_module_metadata_path`.
    """

    return packaged_module_metadata_path(module_name, registry_entry, registry).parent
