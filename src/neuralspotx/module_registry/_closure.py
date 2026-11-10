"""Dependency-closure and reverse-dependency resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError, NSXModuleError
from ..board_plan import resolve_board_plan
from ..metadata import is_compatible
from ..models import ModuleMetadata
from ._bsp import bind_requirements, participant_metadata_path, read_participant, validate_bsp_offer
from ._metadata import _load_module_metadata, metadata_cache_scope
from ._nsx_cfg import _local_module_names, _vendored_module_names
from ._policy import _validate_board_module_dep_policy, _validate_sdk_provider_policy
from ._requirements import requirement_metadata_error, validate_requirement
from ._vendoring import _acquire_modules_for_app


def _compat_check_skipped() -> bool:
    """Whether ``NSX_SKIP_COMPAT_CHECK`` requests bypassing compat enforcement.

    Per-target compatibility is enforced here, in the closure resolver, so the
    documented emergency bypass must be honored at this point (the
    ``is_compatible`` gate below is the single enforcement site; nothing
    downstream re-checks).
    """

    return os.environ.get("NSX_SKIP_COMPAT_CHECK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _resolve_module_closure(
    seed_modules: list[str],
    *,
    app_dir: Path | None,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    default_toolchain: str,
    acquire_missing: bool = False,
) -> list[str]:
    with metadata_cache_scope():
        return _resolve_module_closure_inner(
            seed_modules,
            app_dir=app_dir,
            nsx_cfg=nsx_cfg,
            registry=registry,
            default_toolchain=default_toolchain,
            acquire_missing=acquire_missing,
        )


def _resolve_module_closure_inner(
    seed_modules: list[str],
    *,
    app_dir: Path | None,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    default_toolchain: str,
    acquire_missing: bool = False,
) -> list[str]:
    target = nsx_cfg.get("target", {})
    board = target.get("board")
    soc = target.get("soc")
    toolchain = nsx_cfg.get("toolchain", default_toolchain)
    if not isinstance(board, str) or not isinstance(soc, str):
        raise NSXConfigError("nsx.yml missing target.board or target.soc")
    if not isinstance(toolchain, str):
        raise NSXConfigError("nsx.yml toolchain must be a string")

    plan = resolve_board_plan(app_dir, nsx_cfg)
    selected_bsp = plan.descriptor.bsp.module if plan else None
    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    opaque_names = local_names | vendored_names

    visited: set[str] = set()
    visiting: set[str] = set()
    resolved: list[str] = []
    metadata_cache: dict[str, ModuleMetadata] = {}
    bsp_inspected: set[str] = set()

    def dfs(module_name: str, *, inspect_local: bool = False) -> None:
        inspect_local = inspect_local or module_name == selected_bsp
        if module_name in visited:
            if not inspect_local or module_name in bsp_inspected:
                return
            # A previous unrelated seed treated this source as opaque. It now
            # participates in the BSP graph and must be inspected normally.
            visited.remove(module_name)
            resolved.remove(module_name)
        # Local / vendored modules are opaque — skip registry metadata lookup.
        if module_name in opaque_names and not inspect_local:
            visited.add(module_name)
            resolved.append(module_name)
            return
        if module_name in visiting:
            raise NSXModuleError(f"Dependency cycle detected at module '{module_name}'")
        visiting.add(module_name)
        if inspect_local:
            bsp_inspected.add(module_name)

        # Acquisition is interleaved with traversal by necessity: a module's
        # dependencies live inside its own nsx-module.yaml, so the graph is
        # discovered incrementally (fetch -> parse -> expand). We cannot compute
        # the full closure up front and acquire afterwards. The local/vendored
        # sets computed once above are reused here so traversal-skipping and
        # acquisition share a single source of truth for what is app-owned.
        if acquire_missing and app_dir is not None:
            _acquire_modules_for_app(
                app_dir,
                [module_name],
                registry,
                local_modules=local_names,
                vendored_modules=vendored_names,
            )

        if module_name in opaque_names:
            if app_dir is None:
                raise NSXModuleError("An app-local BSP requires an app directory")
            module_meta = read_participant(
                module_name, participant_metadata_path(module_name, registry, app_dir, nsx_cfg)
            )
        else:
            module_meta = _load_module_metadata(module_name, registry, app_dir=app_dir)
        if plan and module_name == selected_bsp:
            validate_bsp_offer(plan, module_meta)
        elif module_meta.bsp_offer is not None:
            raise NSXModuleError(f"Unselected BSP provider '{module_name}' entered the closure")
        metadata_cache[module_name] = module_meta

        if not module_meta.supports_ambiqsuite:
            raise NSXModuleError(
                f"Module '{module_name}' is not NSX-eligible (support.ambiqsuite=false)"
            )
        if not _compat_check_skipped() and not is_compatible(
            module_meta.raw,
            board=board,
            soc=soc,
            toolchain=toolchain,
        ):
            raise NSXModuleError(
                f"Module '{module_name}' is incompatible with target "
                f"board={board}, soc={soc}, toolchain={toolchain}. "
                "Remove the board from targets.supported, extend the module's "
                "nsx-module.yaml 'compatibility', or set NSX_SKIP_COMPAT_CHECK=1 "
                "to bypass."
            )

        for dep in bind_requirements(module_meta, plan):
            try:
                dfs(dep.name, inspect_local=inspect_local)
            except (ValueError, NSXConfigError) as exc:
                if dep.version is not None:
                    raise requirement_metadata_error(module_name, dep, exc) from exc
                raise
            validate_requirement(module_name, dep, metadata_cache.get(dep.name))

        visiting.remove(module_name)
        visited.add(module_name)
        resolved.append(module_name)

    for seed in seed_modules:
        dfs(seed)

    resolved = _order_with_present_optional_deps(
        resolved,
        metadata_cache,
        {
            name: [dep.name for dep in bind_requirements(meta, plan)]
            for name, meta in metadata_cache.items()
        },
    )

    for module_name, module_meta in metadata_cache.items():
        _validate_board_module_dep_policy(module_name, module_meta, metadata_cache)
        _validate_sdk_provider_policy(module_name, module_meta, metadata_cache)

    sdk_providers = [
        name for name, meta in metadata_cache.items() if meta.module_type == "sdk_provider"
    ]
    if len(sdk_providers) > 1:
        raise NSXModuleError(
            "Multiple SDK providers resolved in module closure: " + ", ".join(sorted(sdk_providers))
        )

    return resolved


def _order_with_present_optional_deps(
    resolved: list[str],
    metadata_cache: dict[str, ModuleMetadata],
    required_edges: dict[str, list[str]] | None = None,
) -> list[str]:
    """Reorder *resolved* so a present optional dependency precedes its dependent.

    Optional deps never pull a module into the closure, but when the app adds
    one anyway the dependent's CMake usually tests for its target (e.g.
    ``nsx-tflite-micro`` looking for ``nsx::arm_cmsis_nn``), so it must be
    added first. Required cycles were already rejected by the closure walk, so
    required edges are hard constraints. Optional edges are accepted in closure
    order, each only if it cannot form a cycle with the edges accepted before
    it; a rejected optional edge leaves the order to the required edges.
    """

    present = set(resolved)
    # Edges point from a module to the modules that must precede it.
    edges: dict[str, list[str]] = {}
    for module_name in resolved:
        module_meta = metadata_cache.get(module_name)
        edges[module_name] = (
            [
                dep
                for dep in (
                    required_edges.get(module_name, [])
                    if required_edges is not None
                    else module_meta.required_deps
                )
                if dep in present
            ]
            if module_meta is not None
            else []
        )

    def must_follow(module_name: str, target: str) -> bool:
        """Whether accepted edges already place *module_name* after *target*."""
        stack = [module_name]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(edges[current])
        return False

    for module_name in resolved:
        module_meta = metadata_cache.get(module_name)
        if module_meta is None:
            continue
        for dep_name in module_meta.optional_deps:
            if (
                dep_name in present
                and dep_name not in edges[module_name]
                and not must_follow(dep_name, module_name)
            ):
                edges[module_name].append(dep_name)

    ordered: list[str] = []
    done: set[str] = set()
    active: set[str] = set()

    def visit(module_name: str) -> None:
        if module_name in done:
            return
        if module_name in active:
            # Unreachable: every accepted edge was checked against the graph.
            raise NSXModuleError(f"Dependency cycle detected at module '{module_name}'")
        active.add(module_name)
        for dep_name in edges[module_name]:
            visit(dep_name)
        active.remove(module_name)
        done.add(module_name)
        ordered.append(module_name)

    for module_name in resolved:
        visit(module_name)
    return ordered


def _module_dependents(
    module_names: list[str],
    registry: dict[str, Any],
    app_dir: Path | None = None,
    *,
    local_modules: set[str] | None = None,
) -> dict[str, set[str]]:
    skip = local_modules or set()
    dependents = {name: set() for name in module_names}
    with metadata_cache_scope():
        for name in module_names:
            if name in skip:
                continue
            metadata = _load_module_metadata(name, registry, app_dir=app_dir)
            for dep in metadata.required_deps:
                if dep in dependents:
                    dependents[dep].add(name)
    return dependents
