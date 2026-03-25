"""NSX west-backed workspace helper and module metadata orchestrator."""

from __future__ import annotations

import argparse
import copy
import importlib.resources as resources
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from . import operations
from .metadata import (
    RegistryModuleEntry,
    is_compatible,
    load_registry_lock,
    load_yaml,
    registry_entry_for_module,
    validate_nsx_module_metadata,
)
from .subprocess_utils import format_subprocess_error
from .subprocess_utils import run as _run
from .tooling import require_tool as _require_tool
from .tooling import tool_cmd as _tool_cmd

DEFAULT_SOC_FOR_BOARD = {
    "apollo3_evb": "apollo3",
    "apollo3_evb_cygnus": "apollo3",
    "apollo3p_evb": "apollo3p",
    "apollo3p_evb_cygnus": "apollo3p",
    "apollo4l_evb": "apollo4l",
    "apollo4l_blue_evb": "apollo4l",
    "apollo4p_evb": "apollo4p",
    "apollo4p_blue_kbr_evb": "apollo4p",
    "apollo4p_blue_kxr_evb": "apollo4p",
    "apollo5b_evb": "apollo5b",
    "apollo510_evb": "apollo510",
    "apollo510b_evb": "apollo510b",
    "apollo330mP_evb": "apollo330P",
}

DEFAULT_TOOLCHAIN = "arm-none-eabi-gcc"
DEFAULT_REPO_NAME = "neuralspotx"
VERBOSE = 0

WEST_MANIFEST_TEMPLATE = """manifest:
  version: "0.13"

  projects:
    - name: "__NSX_REPO_NAME__"
      url: "__NSX_REPO_URL__"
      revision: "__NSX_REVISION__"
      path: "__NSX_REPO_NAME__"
__AMBIQ_PROJECT_BLOCK__  self:
    path: manifest
"""

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_registry() -> dict[str, Any]:
    registry_resource = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(registry_resource) as registry_path:
        return load_registry_lock(registry_path)


def _effective_registry(base_registry: dict[str, Any], nsx_cfg: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base_registry)
    overrides = nsx_cfg.get("module_registry", {})
    if not isinstance(overrides, dict):
        return merged

    projects = overrides.get("projects", {})
    modules = overrides.get("modules", {})
    if not isinstance(projects, dict) or not isinstance(modules, dict):
        return merged

    merged.setdefault("projects", {})
    merged.setdefault("modules", {})
    for name, override in projects.items():
        if not isinstance(name, str) or not isinstance(override, dict):
            continue
        current = merged["projects"].get(name, {})
        if not isinstance(current, dict):
            current = {}
        current.update(override)
        merged["projects"][name] = current
    for name, override in modules.items():
        if not isinstance(name, str) or not isinstance(override, dict):
            continue
        current = merged["modules"].get(name, {})
        if not isinstance(current, dict):
            current = {}
        current.update(override)
        merged["modules"][name] = current
    return merged


def _registry_project_entry(registry: dict[str, Any], project_name: str) -> dict[str, Any]:
    projects = registry.get("projects", {})
    if not isinstance(projects, dict):
        return {}
    entry = projects.get(project_name, {})
    return entry if isinstance(entry, dict) else {}


def _render_west_manifest(
    nsx_repo_url: str,
    nsx_revision: str,
    ambiqsuite_url: str | None,
    ambiqsuite_revision: str,
) -> str:
    if ambiqsuite_url:
        ambiq_block = (
            "\n"
            "    - name: \"ambiqsuite\"\n"
            f"      url: \"{ambiqsuite_url}\"\n"
            f"      revision: \"{ambiqsuite_revision}\"\n"
            "      path: \"modules/ambiqsuite\"\n"
        )
    else:
        ambiq_block = ""

    return (
        WEST_MANIFEST_TEMPLATE.replace("__NSX_REPO_NAME__", DEFAULT_REPO_NAME)
        .replace("__NSX_REPO_URL__", nsx_repo_url)
        .replace("__NSX_REVISION__", nsx_revision)
        .replace("__AMBIQ_PROJECT_BLOCK__", ambiq_block)
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _copy_packaged_tree(package: str, relative_path: str, destination: Path) -> None:
    resource_root = resources.files(package).joinpath(relative_path)
    with resources.as_file(resource_root) as source_path:
        if not source_path.exists():
            raise SystemExit(f"Packaged resource path not found: {package}:{relative_path}")
        shutil.copytree(
            source_path,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )


def _write_app_module_file(
    app_dir: Path,
    nsx_cfg: dict[str, Any],
) -> None:
    module_names = _module_names_from_nsx(nsx_cfg)
    lines = [
        "# Auto-generated by nsx. Edit via `nsx module ...` commands.",
        "set(NSX_APP_MODULES",
    ]
    lines.extend(f'    "{name}"' for name in module_names)
    lines.append(")")
    (app_dir / "cmake" / "nsx" / "modules.cmake").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _vendored_metadata_relpath(metadata: str) -> Path:
    metadata_path = Path(metadata)
    parts = metadata_path.parts
    if len(parts) >= 2 and parts[0] in {"modules", "boards"}:
        return metadata_path
    if len(parts) >= 4 and tuple(parts[:2]) == ("src", "neuralspotx") and parts[2] == "boards":
        return Path("boards") / Path(*parts[3:])
    if tuple(parts[:2]) == ("neuralspotx", "cmake"):
        return Path("cmake") / "nsx" / metadata_path.name
    if tuple(parts[:3]) == ("src", "neuralspotx", "cmake"):
        return Path("cmake") / "nsx" / metadata_path.name
    return metadata_path


def _vendored_target_dir(app_dir: Path, module_name: str, metadata: str) -> Path:
    metadata_path = Path(metadata)
    if metadata_path.is_absolute():
        return app_dir / "modules" / module_name
    relpath = _vendored_metadata_relpath(metadata)
    if relpath.parts and relpath.parts[0] in {"modules", "boards", "cmake"}:
        return app_dir / relpath.parent
    return app_dir / "modules" / module_name


def _metadata_path_relative_to_project(metadata: Path, project_path: str | None) -> Path:
    if not project_path:
        return metadata
    project_parts = Path(project_path).parts
    metadata_parts = metadata.parts
    if metadata_parts[: len(project_parts)] == project_parts:
        remainder = metadata_parts[len(project_parts) :]
        if remainder:
            return Path(*remainder)
    return metadata


def _project_checkout_candidates(
    project_name: str,
    registry: dict[str, Any],
    workspace: Path,
) -> list[Path]:
    project_entry = _registry_project_entry(registry, project_name)
    project_path = project_entry.get("path")
    candidates: list[Path] = []

    local_path = project_entry.get("local_path")
    if isinstance(local_path, str):
        candidates.append(Path(local_path).expanduser())

    if isinstance(project_path, str):
        candidates.append(workspace / project_path)

    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _require_initialized_workspace(workspace: Path) -> None:
    if (workspace / ".west").exists() and (workspace / "manifest" / "west.yml").exists():
        return
    raise SystemExit(
        f"Workspace is not initialized: {workspace}\n"
        "Run `nsx init-workspace <workspace>` before creating apps or syncing modules."
    )


def _metadata_storage_path(app_dir: Path, metadata_path: Path, project_entry: dict[str, Any]) -> str:
    local_path = project_entry.get("local_path")
    if isinstance(local_path, str):
        local_root = Path(local_path).expanduser().resolve()
        try:
            return str(metadata_path.resolve().relative_to(local_root))
        except ValueError:
            pass

    project_path = project_entry.get("path")
    if isinstance(project_path, str):
        project_root = (_workspace_for_app_dir(app_dir) / project_path).resolve()
        try:
            metadata_rel = metadata_path.resolve().relative_to(project_root)
            return str(Path(project_path) / metadata_rel)
        except ValueError:
            pass

    try:
        return str(metadata_path.resolve().relative_to(app_dir.resolve()))
    except ValueError:
        return str(metadata_path.resolve())


def _packaged_metadata_path(metadata: Path) -> Path | None:
    parts = metadata.parts
    if len(parts) >= 4 and tuple(parts[:2]) == ("src", "neuralspotx") and parts[2] == "boards":
        resource = resources.files("neuralspotx").joinpath("boards", *parts[3:])
    elif len(parts) >= 3 and tuple(parts[:3]) == ("src", "neuralspotx", "cmake"):
        resource = resources.files("neuralspotx").joinpath("cmake", *parts[3:])
    else:
        return None

    with resources.as_file(resource) as resource_path:
        if resource_path.exists():
            return resource_path
    return None


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
    project_path = project_entry.get("path") if isinstance(project_entry.get("path"), str) else None
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


def _unique_preserving_order(module_names: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in module_names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _app_name_from_cfg(nsx_cfg: dict[str, Any]) -> str:
    project = nsx_cfg.get("project", {})
    name = project.get("name")
    if not isinstance(name, str) or not name:
        raise SystemExit("nsx.yml missing project.name")
    return name


def _default_build_dir(app_dir: Path, board: str) -> Path:
    return app_dir / "build" / board


def _run_cmake_configure(app_dir: Path, build_dir: Path, board: str) -> None:
    toolchain_file = app_dir / "cmake" / "nsx" / "toolchains" / "arm-none-eabi-gcc.cmake"
    _run(
        [
            "cmake",
            "-S",
            str(app_dir),
            "-B",
            str(build_dir),
            "-G",
            "Ninja",
            f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DNSX_BOARD={board}",
        ]
    )


def _resolve_app_context(args: argparse.Namespace) -> tuple[Path, Path, dict[str, Any], str, str]:
    app_dir = Path(args.app_dir).expanduser().resolve()
    nsx_cfg = _load_app_cfg(app_dir)
    app_name = _app_name_from_cfg(nsx_cfg)
    board = args.board or nsx_cfg.get("target", {}).get("board")
    if not isinstance(board, str) or not board:
        raise SystemExit("Unable to determine target board from args or nsx.yml")
    workspace = _workspace_for_app_dir(app_dir)
    return app_dir, workspace, nsx_cfg, app_name, board


def _workspace_for_app_dir(app_dir: Path) -> Path:
    nsx_cfg = app_dir / "nsx.yml"
    if nsx_cfg.exists():
        cfg = _read_yaml(nsx_cfg)
        west_manifest = cfg.get("west", {}).get("manifest")
        if isinstance(west_manifest, str):
            manifest_path = (app_dir / west_manifest).resolve()
            if manifest_path.exists():
                return manifest_path.parent.parent

    for parent in [app_dir, *app_dir.parents]:
        if (parent / ".west").exists():
            return parent
        if (parent / "manifest" / "west.yml").exists():
            return parent
    if (app_dir / "cmake" / "nsx").exists():
        return app_dir
    raise SystemExit(f"Unable to determine workspace root from app dir: {app_dir}")


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
    project_path = project_entry.get("path") if isinstance(project_entry.get("path"), str) else None
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


def _replace_exact_line(lines: list[str], old: str, new: str) -> list[str]:
    return [new if line == old else line for line in lines]


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
        "toolchain": profile.get("toolchain", DEFAULT_TOOLCHAIN),
        "channel": profile.get("channel", "stable"),
        "profile": _starter_profile_name(board),
        "profile_status": profile.get("status", "active"),
        "modules": [_module_record(name, registry) for name in profile_modules],
        "features": profile.get("features", {}),
        "west": {"manifest": west_manifest_rel},
        "workspace": {
            "layout": "split-root",
            "root_repo": DEFAULT_REPO_NAME,
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
) -> list[str]:
    target = nsx_cfg.get("target", {})
    board = target.get("board")
    soc = target.get("soc")
    toolchain = nsx_cfg.get("toolchain", DEFAULT_TOOLCHAIN)
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
        "root_repo": DEFAULT_REPO_NAME,
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
        project_meta = reg_projects.get(project_name, {})
        if not isinstance(project_meta, dict):
            continue
        if isinstance(project_meta.get("local_path"), str):
            continue
        url = project_meta.get("url")
        revision = project_meta.get("revision")
        path = project_meta.get("path")
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
    reg_projects = registry.get("projects", {})
    projects: list[str] = []
    for module_name in module_names:
        project = registry_entry_for_module(registry, module_name).project
        project_meta = reg_projects.get(project, {})
        if isinstance(project_meta, dict) and isinstance(project_meta.get("local_path"), str):
            continue
        projects.append(project)
    projects = sorted(set(projects))
    if not projects:
        return
    _run(_tool_cmd("west", "update", *projects), cwd=workspace)


def _workspace_has_manifest(workspace: Path) -> bool:
    return (workspace / "manifest" / "west.yml").exists()


def _ensure_workspace_projects_for_modules(
    workspace: Path,
    nsx_cfg: dict[str, Any],
    registry: dict[str, Any],
    module_names: list[str],
    *,
    sync: bool,
) -> None:
    if not _workspace_has_manifest(workspace):
        return
    temp_cfg = copy.deepcopy(nsx_cfg)
    _update_nsx_cfg_modules(temp_cfg, module_names, registry)
    _update_workspace_manifest(workspace, temp_cfg, registry)
    if sync:
        _sync_projects_for_modules(workspace, module_names, registry)


def _load_app_cfg(app_dir: Path) -> dict[str, Any]:
    cfg_path = app_dir / "nsx.yml"
    if not cfg_path.exists():
        raise SystemExit(f"App config not found: {cfg_path}")
    cfg = _read_yaml(cfg_path)
    if cfg.get("schema_version") != 1:
        raise SystemExit(f"{cfg_path}: unsupported schema_version={cfg.get('schema_version')}")
    return cfg


def _save_app_cfg(app_dir: Path, cfg: dict[str, Any]) -> None:
    _write_yaml(app_dir / "nsx.yml", cfg)


def _manifest_projects_by_name(workspace: Path) -> dict[str, dict[str, Any]]:
    manifest_path = workspace / "manifest" / "west.yml"
    data = _read_yaml(manifest_path)
    manifest = data.get("manifest", {})
    projects = manifest.get("projects", [])
    if not isinstance(projects, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        name = proj.get("name")
        if isinstance(name, str):
            out[name] = proj
    return out


def _print_module_table(registry: dict[str, Any], enabled: set[str]) -> None:
    print("Available NSX modules:")
    for name in sorted(registry["modules"].keys()):
        marker = "*" if name in enabled else " "
        entry = registry_entry_for_module(registry, name)
        print(f"  {marker} {name}  (project={entry.project}, revision={entry.revision})")


def cmd_init_workspace(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).expanduser().resolve()
    operations.init_workspace_impl(
        workspace,
        nsx_repo_url=args.nsx_repo_url,
        nsx_revision=args.nsx_revision,
        ambiqsuite_repo_url=args.ambiqsuite_repo_url,
        ambiqsuite_revision=args.ambiqsuite_revision,
        skip_update=args.skip_update,
    )


def init_workspace_impl(
    workspace: Path,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    operations.init_workspace_impl(
        workspace,
        nsx_repo_url=nsx_repo_url,
        nsx_revision=nsx_revision,
        ambiqsuite_repo_url=ambiqsuite_repo_url,
        ambiqsuite_revision=ambiqsuite_revision,
        skip_update=skip_update,
    )


def cmd_create_app(args: argparse.Namespace) -> None:
    operations.create_app_impl(
        Path(args.workspace).expanduser().resolve(),
        args.name,
        board=args.board,
        soc=args.soc,
        force=args.force,
        init_workspace=args.init_workspace,
        no_bootstrap=args.no_bootstrap,
        no_sync=args.no_sync,
    )


def create_app_impl(
    workspace: Path,
    app_name: str,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    init_workspace: bool = False,
    no_bootstrap: bool = False,
    no_sync: bool = False,
) -> Path:
    return operations.create_app_impl(
        workspace,
        app_name,
        board=board,
        soc=soc,
        force=force,
        init_workspace=init_workspace,
        no_bootstrap=no_bootstrap,
        no_sync=no_sync,
    )


def cmd_sync(args: argparse.Namespace) -> None:
    operations.sync_workspace_impl(Path(args.workspace).expanduser().resolve())


def sync_workspace_impl(workspace: Path) -> None:
    operations.sync_workspace_impl(workspace)


def cmd_doctor(args: argparse.Namespace) -> None:
    operations.doctor_impl()


def doctor_impl() -> None:
    operations.doctor_impl()


def cmd_configure(args: argparse.Namespace) -> None:
    operations.configure_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
    )


def cmd_build(args: argparse.Namespace) -> None:
    operations.build_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        target=args.target,
        jobs=args.jobs,
    )


def cmd_flash(args: argparse.Namespace) -> None:
    operations.flash_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        jobs=args.jobs,
    )


def _resolve_build_context(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> tuple[Path, str, str, Path]:
    resolved_app_dir, _, _, app_name, resolved_board = _resolve_app_context(
        argparse.Namespace(app_dir=str(app_dir), board=board)
    )
    resolved_build_dir = build_dir or _default_build_dir(resolved_app_dir, resolved_board)
    return resolved_app_dir, app_name, resolved_board, resolved_build_dir


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    return operations.configure_app_impl(app_dir, board=board, build_dir=build_dir)


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    target: str | None = None,
    jobs: int = 8,
) -> Path:
    return operations.build_app_impl(
        app_dir,
        board=board,
        build_dir=build_dir,
        target=target,
        jobs=jobs,
    )


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    jobs: int = 8,
) -> Path:
    return operations.flash_app_impl(
        app_dir,
        board=board,
        build_dir=build_dir,
        jobs=jobs,
    )


def cmd_view(args: argparse.Namespace) -> None:
    operations.view_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
    )


def view_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    return operations.view_app_impl(app_dir, board=board, build_dir=build_dir)


def cmd_clean(args: argparse.Namespace) -> None:
    operations.clean_app_impl(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        full=args.full,
    )


def clean_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    full: bool = False,
) -> Path:
    return operations.clean_app_impl(app_dir, board=board, build_dir=build_dir, full=full)


def cmd_module_list(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)
    enabled = set(_module_names_from_nsx(nsx_cfg))
    _print_module_table(registry, enabled)


def cmd_module_add(args: argparse.Namespace) -> None:
    operations.add_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    return operations.add_module_impl(app_dir, module_name, dry_run=dry_run, no_sync=no_sync)


def cmd_module_remove(args: argparse.Namespace) -> None:
    operations.remove_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> tuple[list[str], list[str]]:
    return operations.remove_module_impl(app_dir, module_name, dry_run=dry_run, no_sync=no_sync)


def cmd_module_update(args: argparse.Namespace) -> None:
    operations.update_modules_impl(
        Path(args.app_dir).expanduser().resolve(),
        module_name=args.module,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    return operations.update_modules_impl(
        app_dir,
        module_name=module_name,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def cmd_module_register(args: argparse.Namespace) -> None:
    operations.register_module_impl(
        Path(args.app_dir).expanduser().resolve(),
        args.module,
        metadata=Path(args.metadata).expanduser(),
        project=args.project,
        project_url=args.project_url,
        project_revision=args.project_revision,
        project_path=args.project_path,
        project_local_path=Path(args.project_local_path).expanduser().resolve()
        if args.project_local_path
        else None,
        override=args.override,
        dry_run=args.dry_run,
        no_sync=args.no_sync,
    )


def register_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    metadata: Path,
    project: str,
    project_url: str | None = None,
    project_revision: str | None = None,
    project_path: str | None = None,
    project_local_path: Path | None = None,
    override: bool = False,
    dry_run: bool = False,
    no_sync: bool = False,
) -> Path:
    return operations.register_module_impl(
        app_dir,
        module_name,
        metadata=metadata,
        project=project,
        project_url=project_url,
        project_revision=project_revision,
        project_path=project_path,
        project_local_path=project_local_path,
        override=override,
        dry_run=dry_run,
        no_sync=no_sync,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NSX workspace-first helper for creating and building bare-metal Ambiq apps"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase CLI verbosity. Repeat for more detail.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-workspace", help="Create west manifest + init/update workspace")
    p_init.add_argument("workspace", help="Workspace directory to initialize")
    p_init.add_argument("--nsx-repo-url", default=None, help="NSX repo URL (default: packaged registry upstream URL)")
    p_init.add_argument("--nsx-revision", default="main", help="NSX revision/branch/tag")
    p_init.add_argument("--ambiqsuite-repo-url", default=None, help="Optional AmbiqSuite repo URL")
    p_init.add_argument("--ambiqsuite-revision", default="main", help="Optional AmbiqSuite revision")
    p_init.add_argument("--skip-update", action="store_true", help="Initialize manifest but skip west update")
    p_init.set_defaults(func=cmd_init_workspace)

    p_new = sub.add_parser("create-app", help="Create a new app in an initialized NSX workspace")
    p_new.add_argument("workspace", help="Workspace root")
    p_new.add_argument("name", help="Application name")
    p_new.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new.add_argument("--soc", default=None, help="Target SoC package suffix (default inferred from board)")
    p_new.add_argument("--force", action="store_true", help="Allow writing into a non-empty app directory")
    p_new.add_argument(
        "--init-workspace",
        action="store_true",
        help="Initialize the workspace first if it has not been set up yet",
    )
    p_new.add_argument("--no-bootstrap", action="store_true", help="Create the app without vendoring starter modules")
    p_new.add_argument("--no-sync", action="store_true", help="Skip west update for built-in module projects during app creation")
    p_new.set_defaults(func=cmd_create_app)

    p_new_alias = sub.add_parser("new", help="Alias for create-app")
    p_new_alias.add_argument("workspace", help="Workspace root")
    p_new_alias.add_argument("name", help="Application name")
    p_new_alias.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new_alias.add_argument("--soc", default=None, help="Target SoC package suffix (default inferred from board)")
    p_new_alias.add_argument("--force", action="store_true", help="Allow writing into a non-empty app directory")
    p_new_alias.add_argument(
        "--init-workspace",
        action="store_true",
        help="Initialize the workspace first if it has not been set up yet",
    )
    p_new_alias.add_argument("--no-bootstrap", action="store_true", help="Create the app without vendoring starter modules")
    p_new_alias.add_argument("--no-sync", action="store_true", help="Skip west update for built-in module projects during app creation")
    p_new_alias.set_defaults(func=cmd_create_app)

    p_sync = sub.add_parser("sync", help="Run west update in an existing workspace")
    p_sync.add_argument("workspace", help="Workspace root")
    p_sync.set_defaults(func=cmd_sync)

    p_doctor = sub.add_parser("doctor", help="Check the local NSX toolchain environment")
    p_doctor.set_defaults(func=cmd_doctor)

    p_configure = sub.add_parser("configure", help="Configure a generated NSX app with CMake")
    p_configure.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_configure.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_configure.add_argument("--build-dir", default=None, help="Build directory override")
    p_configure.set_defaults(func=cmd_configure)

    p_build = sub.add_parser("build", help="Build a generated NSX app")
    p_build.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_build.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_build.add_argument("--build-dir", default=None, help="Build directory override")
    p_build.add_argument("--target", default=None, help="Optional explicit build target")
    p_build.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_build.set_defaults(func=cmd_build)

    p_flash = sub.add_parser("flash", help="Build and flash a generated NSX app")
    p_flash.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_flash.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_flash.add_argument("--build-dir", default=None, help="Build directory override")
    p_flash.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_flash.set_defaults(func=cmd_flash)

    p_view = sub.add_parser("view", help="Open the SEGGER SWO viewer for a generated NSX app")
    p_view.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_view.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_view.add_argument("--build-dir", default=None, help="Build directory override")
    p_view.set_defaults(func=cmd_view)

    p_clean = sub.add_parser("clean", help="Clean a generated NSX app build directory")
    p_clean.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_clean.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_clean.add_argument("--build-dir", default=None, help="Build directory override")
    p_clean.add_argument(
        "--full",
        action="store_true",
        help="Remove the full build directory instead of only running the build-system clean target",
    )
    p_clean.set_defaults(func=cmd_clean)

    p_mod = sub.add_parser("module", help="Manage app-local NSX modules")
    mod_sub = p_mod.add_subparsers(dest="module_command", required=True)

    p_mod_list = mod_sub.add_parser("list", help="List available modules and mark enabled ones")
    p_mod_list.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_list.set_defaults(func=cmd_module_list)

    p_mod_add = mod_sub.add_parser("add", help="Enable a module for an app")
    p_mod_add.add_argument("module", help="Module name to enable")
    p_mod_add.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_add.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_add.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_add.set_defaults(func=cmd_module_add)

    p_mod_remove = mod_sub.add_parser("remove", help="Disable a module for an app")
    p_mod_remove.add_argument("module", help="Module name to remove")
    p_mod_remove.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_remove.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_remove.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_remove.set_defaults(func=cmd_module_remove)

    p_mod_update = mod_sub.add_parser("update", help="Refresh enabled modules to current registry revisions")
    p_mod_update.add_argument("module", nargs="?", default=None, help="Optional single module to refresh")
    p_mod_update.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_update.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_update.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_update.set_defaults(func=cmd_module_update)

    p_mod_register = mod_sub.add_parser("register", help="Register an external module for a single app")
    p_mod_register.add_argument("module", help="Module name")
    p_mod_register.add_argument("--metadata", required=True, help="Path to nsx-module.yaml")
    p_mod_register.add_argument("--project", required=True, help="Project/repo key")
    p_mod_register.add_argument("--project-url", default=None, help="west project URL")
    p_mod_register.add_argument("--project-revision", default=None, help="west project revision")
    p_mod_register.add_argument("--project-path", default=None, help="west project path")
    p_mod_register.add_argument("--project-local-path", default=None, help="Local filesystem module path")
    p_mod_register.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_register.add_argument("--override", action="store_true", help="Override existing module entry")
    p_mod_register.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_register.add_argument("--no-sync", action="store_true", help="Skip west update after manifest changes")
    p_mod_register.set_defaults(func=cmd_module_register)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    global VERBOSE
    VERBOSE = args.verbose
    operations.set_verbosity(args.verbose)
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        if VERBOSE > 0:
            raise
        raise SystemExit(format_subprocess_error(exc, context="Command")) from None
    return 0
