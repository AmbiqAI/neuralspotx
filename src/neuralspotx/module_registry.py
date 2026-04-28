"""Helpers for module metadata resolution, dependency closure, and git-based management."""

from __future__ import annotations

import copy
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from .metadata import (
    RegistryModuleEntry,
    is_compatible,
    registry_entry_for_module,
    validate_nsx_module_metadata,
)
from .project_config import (
    _is_packaged_module,
    _metadata_path_relative_to_project,
    _module_clone_dir,
    _packaged_metadata_path,
    _read_yaml,
    _registry_project_entry,
    _unique_preserving_order,
    _vendored_metadata_relpath,
    _vendored_target_dir,
)
from .subprocess_utils import (
    git_clone,
    git_clone_at_commit,
)
from .tooling import require_tool as _require_tool


def _rmtree(path: Path) -> None:
    """Remove a directory tree, handling read-only files on Windows.

    Git pack-index files are marked read-only; ``shutil.rmtree`` fails
    on Windows unless we clear the read-only flag first.
    """

    def _on_rm_error(_func, _path, _exc_info):  # noqa: ANN001
        os.chmod(_path, stat.S_IWRITE)
        os.unlink(_path)

    shutil.rmtree(path, onerror=_on_rm_error)


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
        raise SystemExit(
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
    raise SystemExit(
        f"Unable to locate nsx-module.yaml for module '{module_name}'. "
        f"Searched: {', '.join(searched)}"
    )


def _load_module_metadata(
    module_name: str,
    registry: dict[str, Any],
    app_dir: Path | None = None,
) -> dict[str, Any]:
    entry = registry_entry_for_module(registry, module_name)
    metadata_path = _module_metadata_path(module_name, entry, registry, app_dir=app_dir)
    data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(data, str(metadata_path))
    return data


def _ensure_module_cloned(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Ensure a git-hosted module's project is present in the app.

    The module is cloned from its registry URL, then the ``.git``
    directory is removed so the result is a plain copy — not a nested
    git repository.  This keeps the ``modules/`` directory safely
    gitignored: ``nsx configure`` will re-clone any missing modules.
    """

    if _is_packaged_module(registry, module_name):
        return  # packaged modules are copied, not cloned

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)

    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return  # user-registered local module, vendor instead of clone

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)
    if clone_dir.exists():
        return  # already present

    url = project_entry.url
    if not url:
        raise SystemExit(
            f"Module '{module_name}' project '{entry.project}' has no URL in registry. "
            "Cannot clone."
        )

    _require_tool("git")
    git_clone(url, clone_dir, revision=entry.revision)

    # Remove .git so the module is a plain copy, not a nested repo.
    git_dir = clone_dir / ".git"
    if git_dir.exists():
        _rmtree(git_dir)


def _update_module_clone(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Re-acquire a module at the registry revision.

    Since cloned modules have their ``.git`` directory removed (they are
    plain copies), an update deletes the existing copy and re-clones at
    the desired revision.
    """

    if _is_packaged_module(registry, module_name):
        return

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)
    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)
    if clone_dir.exists():
        _rmtree(clone_dir)
    _ensure_module_cloned(app_dir, module_name, registry)


def _vendor_git_module_at_commit(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
    commit: str,
) -> None:
    """Re-vendor a git module at an exact commit SHA.

    Used by ``nsx sync`` to faithfully restore an ``nsx.lock`` entry,
    independent of where the module's branch currently points. A full
    clone is performed (shallow clones may not contain the commit), the
    requested commit is checked out detached, and ``.git`` is stripped.
    """

    if _is_packaged_module(registry, module_name):
        return

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)

    # User-registered local modules: copy from local_path; ignore commit.
    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return

    url = project_entry.url
    if not url:
        raise SystemExit(
            f"Module '{module_name}' project '{entry.project}' has no URL in registry; cannot sync."
        )

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)
    if clone_dir.exists():
        _rmtree(clone_dir)

    _require_tool("git")
    git_clone_at_commit(url, clone_dir, commit)

    git_dir = clone_dir / ".git"
    if git_dir.exists():
        _rmtree(git_dir)


def _vendor_local_module_into_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Copy a user-registered local module into the app's modules/ directory."""

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)
    if not project_entry.local_path:
        return

    source_dir = Path(project_entry.local_path).expanduser().resolve()
    destination_dir = _module_clone_dir(app_dir, entry.project, registry)

    if destination_dir.resolve() == source_dir.resolve():
        return
    if destination_dir.resolve().is_relative_to(source_dir.resolve()):
        return
    if source_dir.resolve().is_relative_to(destination_dir.resolve()):
        return

    if destination_dir.exists():
        _rmtree(destination_dir)
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        destination_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
    )


def _vendor_packaged_module_into_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Copy a packaged module (board/cmake) from the neuralspotx package into the app."""

    if not _is_packaged_module(registry, module_name):
        return  # git-hosted modules are cloned, not copied

    entry = registry_entry_for_module(registry, module_name)
    source_metadata = _module_metadata_path(module_name, entry, registry, app_dir=app_dir)
    destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)

    source_dir = source_metadata.parent

    if destination_dir.resolve() == source_dir.resolve():
        return
    if destination_dir.resolve().is_relative_to(source_dir.resolve()):
        return

    preserve_existing = destination_dir == app_dir / "cmake" / "nsx"
    if destination_dir.exists() and not preserve_existing:
        _rmtree(destination_dir)
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        destination_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
    )


def _remove_vendored_module_from_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    if _is_packaged_module(registry, module_name):
        entry = registry_entry_for_module(registry, module_name)
        destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)
        if destination_dir == app_dir / "cmake" / "nsx":
            return
        if destination_dir.exists():
            _rmtree(destination_dir)
    else:
        entry = registry_entry_for_module(registry, module_name)
        clone_dir = _module_clone_dir(app_dir, entry.project, registry)
        if clone_dir.exists():
            _rmtree(clone_dir)


def _acquire_modules_for_app(
    app_dir: Path,
    module_names: list[str],
    registry: dict[str, Any],
    *,
    local_modules: set[str] | None = None,
    vendored_modules: set[str] | None = None,
) -> None:
    """Clone or copy all modules needed by an app.

    Modules whose names appear in *local_modules* or *vendored_modules*
    are skipped — they live inside the app tree and are source-controlled
    by the user. (The two sets exist separately so that ``nsx sync`` can
    enforce different invariants on each.)
    """

    skip = (local_modules or set()) | (vendored_modules or set())
    for module_name in module_names:
        if module_name in skip:
            continue
        if _is_packaged_module(registry, module_name):
            _vendor_packaged_module_into_app(app_dir, module_name, registry)
        else:
            _ensure_module_cloned(app_dir, module_name, registry)


def _starter_profile_name(board: str) -> str:
    return f"{board}_minimal"


def _resolve_profile(registry: dict[str, Any], board: str) -> dict[str, Any]:
    name = _starter_profile_name(board)
    profiles = registry["starter_profiles"]
    if name not in profiles:
        raise SystemExit(
            f"No starter profile for board '{board}' in registry.lock (expected profile '{name}')."
        )
    profile = profiles[name]
    if not isinstance(profile, dict):
        raise SystemExit(f"Invalid profile entry '{name}' in registry.lock")
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
        raise SystemExit(f"Invalid modules list in profile for board '{board}'")
    profile_project_overrides = profile.get("project_overrides", {})
    if not isinstance(profile_project_overrides, dict):
        raise SystemExit(f"Invalid project_overrides mapping in profile for board '{board}'")
    profile_module_overrides = profile.get("module_overrides", {})
    if not isinstance(profile_module_overrides, dict):
        raise SystemExit(f"Invalid module_overrides mapping in profile for board '{board}'")

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


def _module_names_from_nsx(nsx_cfg: dict[str, Any]) -> list[str]:
    modules = nsx_cfg.get("modules", [])
    if not isinstance(modules, list):
        raise SystemExit("nsx.yml: 'modules' must be a list")
    names: list[str] = []
    for idx, item in enumerate(modules):
        if not isinstance(item, dict):
            raise SystemExit(f"nsx.yml: modules[{idx}] must be a mapping")
        name = item.get("name")
        if not isinstance(name, str):
            raise SystemExit(f"nsx.yml: modules[{idx}].name must be a string")
        names.append(name)
    return names


def _is_local_module(nsx_cfg: dict[str, Any], module_name: str) -> bool:
    """Return True if *module_name* is marked ``local: true`` in nsx.yml.

    Local modules live inside the app tree (typically ``modules/<name>/``),
    are source-controlled with the app, and are NOT acquired from a registry
    or git remote.
    """
    for item in nsx_cfg.get("modules", []):
        if isinstance(item, dict) and item.get("name") == module_name:
            return bool(item.get("local"))
    return False


def _local_module_names(nsx_cfg: dict[str, Any]) -> set[str]:
    """Return the set of modules linked to a local path on disk.

    Today this is keyed off the legacy ``local: true`` flag (paired with
    a ``module_registry.modules.<name>.local_path`` override). The
    user-facing ``source: { path: <p> }`` shorthand is reserved for a
    future pass and is not yet recognised here.
    """
    return {
        item["name"]
        for item in nsx_cfg.get("modules", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("local")
    }


def _vendored_module_names(nsx_cfg: dict[str, Any]) -> set[str]:
    """Return the set of modules declared as ``source: { vendored: true }``.

    Vendored modules live inside the app tree (``modules/<name>/``), are
    source-controlled with the app, and are NEVER touched by ``nsx sync``
    — useful for AOT-generated modules and custom third-party drops.
    """
    names: set[str] = set()
    for item in nsx_cfg.get("modules", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        source = item.get("source")
        if isinstance(source, dict) and source.get("vendored") is True:
            names.add(name)
    return names


def _validate_board_module_dep_policy(
    module_name: str,
    metadata: dict[str, Any],
    resolver: dict[str, dict[str, Any]],
) -> None:
    if metadata["module"]["type"] != "board":
        return
    required = metadata["depends"]["required"]
    soc_count = 0
    for dep_name in required:
        dep_meta = resolver.get(dep_name)
        if dep_meta is None:
            continue
        if dep_meta["module"]["type"] == "soc":
            soc_count += 1
    if soc_count != 1:
        raise SystemExit(
            f"Board module '{module_name}' must depend on exactly one soc module. "
            f"Found soc dependency count={soc_count}"
        )


def _validate_sdk_provider_policy(
    module_name: str,
    metadata: dict[str, Any],
    resolver: dict[str, dict[str, Any]],
) -> None:
    constraints = metadata.get("constraints", {})
    if not isinstance(constraints, dict):
        return
    required_provider = constraints.get("required_sdk_provider")
    if not isinstance(required_provider, str):
        return

    provider_names = [
        name
        for name, meta in resolver.items()
        if meta.get("module", {}).get("type") == "sdk_provider"
    ]
    if required_provider not in provider_names:
        raise SystemExit(
            f"Module '{module_name}' requires SDK provider '{required_provider}' "
            "but it is not enabled in the resolved dependency closure."
        )


def _resolve_module_closure(
    seed_modules: list[str],
    *,
    app_dir: Path | None,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    default_toolchain: str,
) -> list[str]:
    target = nsx_cfg.get("target", {})
    board = target.get("board")
    soc = target.get("soc")
    toolchain = nsx_cfg.get("toolchain", default_toolchain)
    if not isinstance(board, str) or not isinstance(soc, str):
        raise SystemExit("nsx.yml missing target.board or target.soc")
    if not isinstance(toolchain, str):
        raise SystemExit("nsx.yml toolchain must be a string")

    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    opaque_names = local_names | vendored_names

    visited: set[str] = set()
    visiting: set[str] = set()
    resolved: list[str] = []
    metadata_cache: dict[str, dict[str, Any]] = {}

    def dfs(module_name: str) -> None:
        if module_name in visited:
            return
        # Local / vendored modules are opaque — skip registry metadata lookup.
        if module_name in opaque_names:
            visited.add(module_name)
            resolved.append(module_name)
            return
        if module_name in visiting:
            raise SystemExit(f"Dependency cycle detected at module '{module_name}'")
        visiting.add(module_name)

        module_meta = _load_module_metadata(module_name, registry, app_dir=app_dir)
        metadata_cache[module_name] = module_meta

        if not module_meta["support"]["ambiqsuite"]:
            raise SystemExit(
                f"Module '{module_name}' is not NSX-eligible (support.ambiqsuite=false)"
            )
        if not is_compatible(
            module_meta,
            board=board,
            soc=soc,
            toolchain=toolchain,
        ):
            raise SystemExit(
                f"Module '{module_name}' is incompatible with "
                f"board={board}, soc={soc}, toolchain={toolchain}"
            )

        for dep_name in module_meta["depends"]["required"]:
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
        if meta.get("module", {}).get("type") == "sdk_provider"
    ]
    if len(sdk_providers) > 1:
        raise SystemExit(
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
    for name in module_names:
        if name in skip:
            continue
        metadata = _load_module_metadata(name, registry, app_dir=app_dir)
        for dep in metadata["depends"]["required"]:
            if dep in dependents:
                dependents[dep].add(name)
    return dependents


def _update_nsx_cfg_modules(
    nsx_cfg: dict[str, Any],
    module_names: list[str],
    registry: dict[str, Any],
) -> None:
    # Preserve existing local module entries — they don't come from
    # the registry and must keep their ``local: true`` flag.
    existing_local: dict[str, dict[str, Any]] = {}
    for item in nsx_cfg.get("modules", []):
        if isinstance(item, dict) and item.get("local"):
            existing_local[item["name"]] = item

    new_modules: list[dict[str, Any]] = []
    for name in _unique_preserving_order(module_names):
        if name in existing_local:
            new_modules.append(existing_local[name])
        else:
            new_modules.append(_module_record(name, registry))
    nsx_cfg["modules"] = new_modules


def _print_module_table(
    registry: dict[str, Any],
    enabled: set[str],
    *,
    heading: str = "NSX modules in the active registry (* = enabled for this app):",
) -> None:
    print(heading)
    for name in sorted(registry["modules"].keys()):
        marker = "*" if name in enabled else " "
        entry = registry_entry_for_module(registry, name)
        print(f"  {marker} {name}  (project={entry.project}, revision={entry.revision})")


def _module_discovery_record(
    module_name: str,
    registry: dict[str, Any],
    *,
    app_dir: Path | None = None,
    enabled: bool = False,
    include_metadata: bool = True,
) -> dict[str, Any]:
    entry = registry_entry_for_module(registry, module_name)
    record: dict[str, Any] = {
        "name": module_name,
        "project": entry.project,
        "revision": entry.revision,
        "metadata": entry.metadata,
        "enabled": enabled,
    }
    if not include_metadata:
        return record

    try:
        metadata = _load_module_metadata(module_name, registry, app_dir=app_dir)
    except SystemExit as exc:
        record["metadata_available"] = False
        if app_dir is None:
            record["metadata_error"] = (
                f"{exc} Provide --app-dir to resolve external module metadata."
            )
        else:
            record["metadata_error"] = str(exc)
        return record

    record["metadata_available"] = True
    record["module"] = copy.deepcopy(metadata["module"])
    record["support"] = copy.deepcopy(metadata["support"])
    record["build"] = copy.deepcopy(metadata["build"])
    record["depends"] = copy.deepcopy(metadata["depends"])
    record["compatibility"] = copy.deepcopy(metadata["compatibility"])
    for key in (
        "summary",
        "capabilities",
        "use_cases",
        "anti_use_cases",
        "agent_keywords",
        "example_refs",
        "composition_hints",
    ):
        if key in metadata:
            record[key] = copy.deepcopy(metadata[key])
    for key in ("provides", "constraints", "integrations"):
        if key in metadata:
            record[key] = copy.deepcopy(metadata[key])
    return record


def _module_discovery_records(
    registry: dict[str, Any],
    enabled: set[str],
    *,
    app_dir: Path | None = None,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    return [
        _module_discovery_record(
            name,
            registry,
            app_dir=app_dir,
            enabled=name in enabled,
            include_metadata=include_metadata,
        )
        for name in sorted(registry["modules"].keys())
    ]
