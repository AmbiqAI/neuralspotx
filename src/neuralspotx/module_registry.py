"""Helpers for module metadata resolution, dependency closure, and vendoring."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from .metadata import (
    RegistryModuleEntry,
    is_compatible,
    registry_entry_for_module,
    validate_nsx_module_metadata,
)
from .models import ProjectEntry
from .project_config import (
    _metadata_path_relative_to_project,
    _packaged_metadata_path,
    _project_checkout_candidates,
    _read_yaml,
    _registry_project_entry,
    _unique_preserving_order,
    _vendored_metadata_relpath,
    _vendored_target_dir,
    _workspace_has_manifest,
    _write_yaml,
)
from .subprocess_utils import run as _run
from .tooling import require_tool as _require_tool
from .tooling import tool_cmd as _tool_cmd


def _module_metadata_path(
    module_name: str,
    registry_entry: RegistryModuleEntry,
    registry: dict[str, Any],
    workspace: Path,
    app_dir: Path | None = None,
) -> Path:
    metadata = Path(registry_entry.metadata)
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

    packaged = _packaged_metadata_path(metadata)
    if packaged is not None:
        return packaged

    project_entry = _registry_project_entry(registry, registry_entry.project)
    project_path = project_entry.path
    metadata_rel = _metadata_path_relative_to_project(metadata, project_path)
    searched: list[Path] = []

    for checkout_root in _project_checkout_candidates(registry_entry.project, registry, workspace):
        candidate = checkout_root / metadata_rel
        searched.append(candidate)
        if candidate.exists():
            return candidate

    workspace_path = (workspace / metadata).resolve()
    searched.append(workspace_path)
    if workspace_path.exists():
        return workspace_path

    raise SystemExit(
        f"Unable to locate nsx-module.yaml for module '{module_name}'. "
        f"Searched metadata path '{registry_entry.metadata}' under: "
        + ", ".join(str(p) for p in searched)
    )


def _load_module_metadata(
    module_name: str,
    registry: dict[str, Any],
    workspace: Path,
    app_dir: Path | None = None,
) -> dict[str, Any]:
    entry = registry_entry_for_module(registry, module_name)
    metadata_path = _module_metadata_path(module_name, entry, registry, workspace, app_dir=app_dir)
    data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(data, str(metadata_path))
    return data


def _vendor_module_into_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
    workspace: Path,
) -> None:
    entry = registry_entry_for_module(registry, module_name)
    source_metadata = _module_metadata_path(module_name, entry, registry, workspace)
    destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)

    project_entry = _registry_project_entry(registry, entry.project)
    project_path = project_entry.path
    metadata_rel = _metadata_path_relative_to_project(Path(entry.metadata), project_path)

    source_dir = source_metadata.parent
    if project_path is not None:
        for checkout_root in _project_checkout_candidates(entry.project, registry, workspace):
            candidate_dir = checkout_root / metadata_rel.parent
            if candidate_dir.exists():
                source_dir = candidate_dir
                break

    if destination_dir.resolve() == source_dir.resolve():
        return
    if destination_dir.resolve().is_relative_to(source_dir.resolve()):
        return

    preserve_existing = destination_dir == app_dir / "cmake" / "nsx"
    if destination_dir.exists() and not preserve_existing:
        shutil.rmtree(destination_dir)
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
    entry = registry_entry_for_module(registry, module_name)
    destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)
    if destination_dir == app_dir / "cmake" / "nsx":
        return
    if destination_dir.exists():
        shutil.rmtree(destination_dir)


def _vendor_modules_into_app(
    app_dir: Path,
    module_names: list[str],
    registry: dict[str, Any],
    workspace: Path,
) -> None:
    for module_name in module_names:
        _vendor_module_into_app(app_dir, module_name, registry, workspace)


def _starter_profile_name(board: str) -> str:
    return f"{board}_minimal"


def _resolve_profile(registry: dict[str, Any], board: str) -> dict[str, Any]:
    name = _starter_profile_name(board)
    profiles = registry["starter_profiles"]
    if name not in profiles:
        raise SystemExit(
            f"No starter profile for board '{board}' in registry.lock "
            f"(expected profile '{name}')."
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
    west_manifest_rel: str,
    *,
    default_toolchain: str,
    default_repo_name: str,
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
        "west": {"manifest": west_manifest_rel},
        "workspace": {
            "layout": "split-root",
            "root_repo": default_repo_name,
            "module_dir": "modules",
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
    workspace: Path,
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

    visited: set[str] = set()
    visiting: set[str] = set()
    resolved: list[str] = []
    metadata_cache: dict[str, dict[str, Any]] = {}

    def dfs(module_name: str) -> None:
        if module_name in visited:
            return
        if module_name in visiting:
            raise SystemExit(f"Dependency cycle detected at module '{module_name}'")
        visiting.add(module_name)

        module_meta = _load_module_metadata(module_name, registry, workspace, app_dir=app_dir)
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
            "Multiple SDK providers resolved in module closure: "
            + ", ".join(sorted(sdk_providers))
        )

    return resolved


def _module_dependents(
    module_names: list[str], registry: dict[str, Any], workspace: Path, app_dir: Path | None = None
) -> dict[str, set[str]]:
    dependents = {name: set() for name in module_names}
    for name in module_names:
        metadata = _load_module_metadata(name, registry, workspace, app_dir=app_dir)
        for dep in metadata["depends"]["required"]:
            if dep in dependents:
                dependents[dep].add(name)
    return dependents


def _update_nsx_cfg_modules(
    nsx_cfg: dict[str, Any],
    module_names: list[str],
    registry: dict[str, Any],
) -> None:
    nsx_cfg["modules"] = [
        _module_record(name, registry) for name in _unique_preserving_order(module_names)
    ]


def _update_workspace_manifest(
    workspace: Path,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    *,
    default_repo_name: str,
) -> None:
    manifest_path = workspace / "manifest" / "west.yml"
    if not manifest_path.exists():
        raise SystemExit(f"Cannot update west manifest; file not found: {manifest_path}")
    data = _read_yaml(manifest_path)
    manifest = data.get("manifest")
    if not isinstance(manifest, dict):
        raise SystemExit(f"Invalid west manifest format in {manifest_path}")

    module_names = sorted(_module_names_from_nsx(nsx_cfg))
    data["x-nsx"] = {
        "schema_version": 1,
        "channel": nsx_cfg.get("channel", "stable"),
        "modules": module_names,
        "profile": nsx_cfg.get("profile"),
        "root_repo": default_repo_name,
    }

    projects = manifest.get("projects")
    if not isinstance(projects, list):
        raise SystemExit(f"west.yml manifest.projects must be a list in {manifest_path}")

    project_names = {proj.get("name") for proj in projects if isinstance(proj, dict)}
    reg_projects = registry.get("projects", {})
    for item in nsx_cfg.get("modules", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        entry = registry_entry_for_module(registry, name)
        project_name = entry.project
        if project_name in project_names:
            continue
        project_meta = ProjectEntry.from_mapping(project_name, reg_projects.get(project_name))
        if project_meta.local_path:
            continue
        url = project_meta.url
        revision = project_meta.revision
        path = project_meta.path
        if (
            isinstance(url, str)
            and isinstance(revision, str)
            and isinstance(path, str)
            and not url.startswith("local://")
        ):
            projects.append(
                {
                    "name": project_name,
                    "url": url,
                    "revision": revision,
                    "path": path,
                }
            )
            project_names.add(project_name)

    _write_yaml(manifest_path, data)


def _sync_projects_for_modules(
    workspace: Path,
    module_names: list[str],
    registry: dict[str, Any],
) -> None:
    _require_tool("west")
    projects: list[str] = []
    for module_name in module_names:
        project = registry_entry_for_module(registry, module_name).project
        project_meta = _registry_project_entry(registry, project)
        if project_meta.local_path:
            continue
        projects.append(project)
    projects = sorted(set(projects))
    if not projects:
        return
    _run(_tool_cmd("west", "update", *projects), cwd=workspace)


def _ensure_workspace_projects_for_modules(
    workspace: Path,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    module_names: list[str],
    *,
    sync: bool,
    default_repo_name: str,
) -> None:
    if not _workspace_has_manifest(workspace):
        return
    temp_cfg = copy.deepcopy(nsx_cfg)
    _update_nsx_cfg_modules(temp_cfg, module_names, registry)
    _update_workspace_manifest(
        workspace,
        temp_cfg,
        registry,
        default_repo_name=default_repo_name,
    )
    if sync:
        _sync_projects_for_modules(workspace, module_names, registry)


def _print_module_table(registry: dict[str, Any], enabled: set[str]) -> None:
    print("Available NSX modules:")
    for name in sorted(registry["modules"].keys()):
        marker = "*" if name in enabled else " "
        entry = registry_entry_for_module(registry, name)
        print(f"  {marker} {name}  (project={entry.project}, revision={entry.revision})")
