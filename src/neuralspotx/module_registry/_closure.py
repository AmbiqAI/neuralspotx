"""Dependency-closure and reverse-dependency resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError, NSXModuleError
from ..metadata import is_compatible
from ..models import ModuleMetadata
from ._metadata import _load_module_metadata, metadata_cache_scope
from ._nsx_cfg import _local_module_names, _vendored_module_names
from ._policy import _validate_board_module_dep_policy, _validate_sdk_provider_policy
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

    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    opaque_names = local_names | vendored_names

    visited: set[str] = set()
    visiting: set[str] = set()
    resolved: list[str] = []
    metadata_cache: dict[str, ModuleMetadata] = {}

    def dfs(module_name: str) -> None:
        if module_name in visited:
            return
        # Local / vendored modules are opaque — skip registry metadata lookup.
        if module_name in opaque_names:
            visited.add(module_name)
            resolved.append(module_name)
            return
        if module_name in visiting:
            raise NSXModuleError(f"Dependency cycle detected at module '{module_name}'")
        visiting.add(module_name)

        if acquire_missing and app_dir is not None:
            _acquire_modules_for_app(
                app_dir,
                [module_name],
                registry,
                local_modules=local_names,
                vendored_modules=vendored_names,
            )

        module_meta = _load_module_metadata(module_name, registry, app_dir=app_dir)
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

        for dep_name in module_meta.required_deps:
            dfs(dep_name)

        visiting.remove(module_name)
        visited.add(module_name)
        resolved.append(module_name)

    for seed in seed_modules:
        dfs(seed)

    for module_name, module_meta in metadata_cache.items():
        _validate_board_module_dep_policy(module_name, module_meta, metadata_cache)
        _validate_sdk_provider_policy(module_name, module_meta, metadata_cache)

    sdk_providers = [
        name
        for name, meta in metadata_cache.items()
        if meta.module_type == "sdk_provider"
    ]
    if len(sdk_providers) > 1:
        raise NSXModuleError(
            "Multiple SDK providers resolved in module closure: " + ", ".join(sorted(sdk_providers))
        )

    return resolved


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
