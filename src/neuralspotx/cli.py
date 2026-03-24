"""NSX west-backed workspace helper and module metadata orchestrator."""

from __future__ import annotations

import argparse
import copy
import importlib.resources as resources
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from neuralspotx.metadata import (
    RegistryModuleEntry,
    is_compatible,
    load_registry_lock,
    load_yaml,
    registry_entry_for_module,
    validate_nsx_module_metadata,
)

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


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _run_capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )


def _print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")


def _jlink_failure_hint(output: str) -> str | None:
    lowered = output.lower()
    if "failed to open dll" in lowered:
        return (
            "SEGGER J-Link failed to load its runtime library.\n"
            "Check that the J-Link tools are installed correctly and can run outside `nsx`."
        )
    if "connecting to j-link via usb...failed" in lowered or "cannot connect to j-link" in lowered:
        return (
            "SEGGER J-Link could not connect to the probe over USB.\n"
            "Check the probe connection, power, and that no other tool is holding the J-Link."
        )
    if "cannot connect to target" in lowered or "failed to connect to target" in lowered:
        return (
            "SEGGER J-Link connected, but could not connect to the target device.\n"
            "Check target power, SWD wiring, board selection, and reset state."
        )
    return None


def _format_subprocess_error(exc: subprocess.CalledProcessError, *, context: str) -> str:
    output_parts: list[str] = []
    stdout = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if isinstance(stdout, str) and stdout.strip():
        output_parts.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        output_parts.append(stderr.strip())
    combined_output = "\n".join(output_parts)

    hint = _jlink_failure_hint(combined_output)
    if hint:
        message = f"{context} failed.\n{hint}"
        if VERBOSE == 0:
            message += "\nRe-run with `--verbose` for the full tool output."
        return message

    message = f"{context} failed with exit code {exc.returncode}."
    if VERBOSE == 0:
        message += "\nRe-run with `--verbose` for the full subprocess traceback."
    return message


def _extract_view_command(build_dir: Path, target: str) -> list[str]:
    ninja_file = build_dir / "build.ninja"
    if not ninja_file.exists():
        raise SystemExit(f"Missing build.ninja in build directory: {build_dir}")

    lines = ninja_file.read_text(encoding="utf-8").splitlines()
    block_header = f"build CMakeFiles/{target}"
    for idx, line in enumerate(lines):
        if not line.strip().startswith(block_header):
            continue
        for follow in lines[idx + 1 : idx + 8]:
            stripped = follow.strip()
            if stripped.startswith("COMMAND = "):
                command_text = stripped.removeprefix("COMMAND = ")
                # Ninja emits `cd <dir> && <command>` for custom targets.
                if " && " in command_text:
                    _, command_text = command_text.split(" && ", 1)
                return shlex.split(command_text)
        break

    raise SystemExit(
        f"Unable to resolve the SEGGER SWO viewer command for target '{target}' from {ninja_file}"
    )


def _require_tool(name: str) -> None:
    if shutil.which(name) is None:
        hint = ""
        if name == "west":
            hint = (
                "\nHint: from neuralspotx run:\n"
                "  uv sync\n"
                "  uv run west --version\n"
                "  uv run nsx <command> ..."
            )
        raise SystemExit(f"Required tool not found in PATH: {name}{hint}")


def _tool_path(name: str) -> str | None:
    return shutil.which(name)


def _doctor_check(
    label: str,
    ok: bool,
    *,
    detail: str | None = None,
    hint: str | None = None,
) -> bool:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}")
    if detail:
        print(f"  {detail}")
    if hint and not ok:
        print(f"  Hint: {hint}")
    return ok


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
    _run(["west", "update", *projects], cwd=workspace)


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
    _require_tool("west")
    workspace = Path(args.workspace).expanduser().resolve()
    _init_workspace_impl(
        workspace,
        nsx_repo_url=args.nsx_repo_url,
        nsx_revision=args.nsx_revision,
        ambiqsuite_repo_url=args.ambiqsuite_repo_url,
        ambiqsuite_revision=args.ambiqsuite_revision,
        skip_update=args.skip_update,
    )


def _init_workspace_impl(
    workspace: Path,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    _require_tool("west")

    manifest_dir = workspace / "manifest"
    west_yml = manifest_dir / "west.yml"

    workspace.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    default_nsx_url = _registry_project_entry(_load_registry(), DEFAULT_REPO_NAME).get("url")
    if not isinstance(default_nsx_url, str) or not default_nsx_url:
        raise SystemExit("Built-in registry is missing a default URL for the neuralspotx project.")
    effective_nsx_repo_url = nsx_repo_url or default_nsx_url

    manifest_text = _render_west_manifest(
        nsx_repo_url=effective_nsx_repo_url,
        nsx_revision=nsx_revision,
        ambiqsuite_url=ambiqsuite_repo_url,
        ambiqsuite_revision=ambiqsuite_revision,
    )
    west_yml.write_text(manifest_text, encoding="utf-8")

    if not (workspace / ".west").exists():
        _run(["west", "init", "-l", "manifest"], cwd=workspace)

    if not skip_update:
        _run(["west", "update"], cwd=workspace)

    print(f"NSX workspace initialized at: {workspace}")
    print(f"Root repo path in workspace: {workspace / DEFAULT_REPO_NAME}")
    print(f"Manifest: {west_yml}")


def cmd_create_app(args: argparse.Namespace) -> None:
    base_registry = _load_registry()
    workspace = Path(args.workspace).expanduser().resolve()
    if args.init_workspace and not _workspace_has_manifest(workspace):
        _init_workspace_impl(
            workspace,
            skip_update=args.no_sync and args.no_bootstrap,
        )
    _require_initialized_workspace(workspace)
    app_name = args.name

    soc = args.soc or DEFAULT_SOC_FOR_BOARD.get(args.board)
    if soc is None:
        raise SystemExit(
            f"Unable to infer --soc for board '{args.board}'. Pass --soc explicitly."
        )

    template_root = resources.files("neuralspotx.templates").joinpath("external_app")
    with resources.as_file(template_root) as src_template:
        if not src_template.exists():
            raise SystemExit(f"Template directory not found: {src_template}")

        app_dir = workspace / "apps" / app_name
        if app_dir.exists() and any(app_dir.iterdir()) and not args.force:
            raise SystemExit(f"App directory already exists and is not empty: {app_dir}")

        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_template, app_dir, dirs_exist_ok=True)

    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")

    cmake_file = app_dir / "CMakeLists.txt"
    lines = cmake_file.read_text(encoding="utf-8").splitlines()
    lines = _replace_exact_line(
        lines, "project(__NSX_APP_NAME__ LANGUAGES C CXX ASM)", f"project({app_name} LANGUAGES C CXX ASM)"
    )
    lines = _replace_exact_line(lines, "add_executable(__NSX_APP_NAME__", f"add_executable({app_name}")
    lines = _replace_exact_line(
        lines, "target_link_libraries(__NSX_APP_NAME__ PRIVATE", f"target_link_libraries({app_name} PRIVATE"
    )
    lines = _replace_exact_line(
        lines, "target_link_options(__NSX_APP_NAME__ PRIVATE", f"target_link_options({app_name} PRIVATE"
    )
    lines = _replace_exact_line(
        lines,
        "    target_link_libraries(__NSX_APP_NAME__ PRIVATE nsx::portable_api)",
        f"    target_link_libraries({app_name} PRIVATE nsx::portable_api)",
    )
    lines = _replace_exact_line(
        lines, "    add_custom_command(TARGET __NSX_APP_NAME__ POST_BUILD", f"    add_custom_command(TARGET {app_name} POST_BUILD"
    )
    lines = _replace_exact_line(
        lines,
        "        COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:__NSX_APP_NAME__> $<TARGET_FILE_DIR:__NSX_APP_NAME__>/__NSX_APP_NAME__.bin",
        f"        COMMAND ${{CMAKE_OBJCOPY}} -Obinary $<TARGET_FILE:{app_name}> $<TARGET_FILE_DIR:{app_name}>/{app_name}.bin",
    )
    lines = _replace_exact_line(
        lines, '        COMMENT "Generating __NSX_APP_NAME__.bin")', f'        COMMENT "Generating {app_name}.bin")'
    )
    lines = _replace_exact_line(
        lines, "        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:__NSX_APP_NAME__>", f"        COMMAND ${{CMAKE_SIZE}} $<TARGET_FILE:{app_name}>"
    )
    lines = _replace_exact_line(lines, "nsx_finalize_app(__NSX_APP_NAME__)", f"nsx_finalize_app({app_name})")
    lines = _replace_exact_line(
        lines, "    -Wl,-Map,$<TARGET_FILE_DIR:__NSX_APP_NAME__>/__NSX_APP_NAME__.map", f"    -Wl,-Map,$<TARGET_FILE_DIR:{app_name}>/{app_name}.map"
    )
    lines = _replace_exact_line(lines, "find_package(nsx_soc_apollo510 REQUIRED CONFIG)", f"find_package(nsx_soc_{soc} REQUIRED CONFIG)")
    lines = _replace_exact_line(
        lines, "find_package(nsx_board_apollo510_evb REQUIRED CONFIG)", f"find_package(nsx_board_{args.board} REQUIRED CONFIG)"
    )
    lines = _replace_exact_line(lines, "    nsx::board_apollo510_evb", f"    nsx::board_{args.board}")

    if args.board != "apollo510_evb":
        lines = [
            line
            for line in lines
            if not line.startswith("set(NSX_SEGGER_")
        ]

    cmake_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    nsx_cfg = _generate_nsx_config(
        app_name=app_name,
        board=args.board,
        soc=soc,
        registry=base_registry,
        west_manifest_rel="../../manifest/west.yml",
    )
    if args.no_bootstrap:
        nsx_cfg["modules"] = []
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        print(f"Created app '{app_name}' at: {app_dir}")
        print("Starter modules were not bootstrapped (--no-bootstrap).")
        print("Next steps:")
        print(f"  1) cd {app_dir}")
        print("  2) Run `uv run nsx module list --app-dir .`")
        print("  3) Add modules with `uv run nsx module add <module> --app-dir .`")
        return

    registry = _effective_registry(base_registry, nsx_cfg)
    _ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        _module_names_from_nsx(nsx_cfg),
        sync=not args.no_sync,
    )
    starter_modules = _resolve_module_closure(
        _module_names_from_nsx(nsx_cfg),
        app_dir=None,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    _ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        starter_modules,
        sync=not args.no_sync,
    )
    _update_nsx_cfg_modules(nsx_cfg, starter_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _vendor_modules_into_app(app_dir, starter_modules, registry, workspace)
    if nsx_cfg.get("profile_status") == "scaffold":
        print(
            f"NOTE: profile '{nsx_cfg.get('profile')}' is scaffold-only. "
            "Build bring-up may not be complete yet."
        )

    print(f"Created app '{app_name}' at: {app_dir}")
    print("Next steps:")
    print(f"  1) cd {app_dir}")
    print("  2) Run `uv run nsx configure --app-dir .`")
    print("  3) Run `uv run nsx build --app-dir .`, `uv run nsx flash --app-dir .`, or `uv run nsx view --app-dir .`")


def cmd_sync(args: argparse.Namespace) -> None:
    _require_tool("west")
    workspace = Path(args.workspace).expanduser().resolve()
    _require_initialized_workspace(workspace)
    _run(["west", "update"], cwd=workspace)


def cmd_doctor(args: argparse.Namespace) -> None:
    all_ok = True

    python_exe = shutil.which("python") or shutil.which("python3")
    all_ok &= _doctor_check("Python", python_exe is not None, detail=python_exe)
    all_ok &= _doctor_check("uv", _tool_path("uv") is not None, detail=_tool_path("uv"))
    all_ok &= _doctor_check("cmake", _tool_path("cmake") is not None, detail=_tool_path("cmake"))
    all_ok &= _doctor_check("ninja", _tool_path("ninja") is not None, detail=_tool_path("ninja"))
    all_ok &= _doctor_check(
        "west",
        _tool_path("west") is not None,
        detail=_tool_path("west"),
        hint="Run `uv sync` in the neuralspotx repo if west is missing.",
    )
    all_ok &= _doctor_check(
        "arm-none-eabi-gcc",
        _tool_path("arm-none-eabi-gcc") is not None,
        detail=_tool_path("arm-none-eabi-gcc"),
        hint="Install the Arm GNU toolchain and ensure it is in PATH.",
    )

    jlink_path = _tool_path("JLinkExe")
    jlink_ok = jlink_path is not None
    all_ok &= _doctor_check(
        "SEGGER JLinkExe",
        jlink_ok,
        detail=jlink_path,
        hint="Install the SEGGER J-Link package and ensure `JLinkExe` is in PATH.",
    )

    swo_path = _tool_path("JLinkSWOViewerCL")
    all_ok &= _doctor_check(
        "SEGGER JLinkSWOViewerCL",
        swo_path is not None,
        detail=swo_path,
        hint="Install the SEGGER J-Link package and ensure `JLinkSWOViewerCL` is in PATH.",
    )

    if jlink_ok:
        try:
            probe = subprocess.run(
                ["JLinkExe", "-CommandFile", "-", "-NoGui", "1"],
                check=True,
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )
            output = (probe.stdout or "") + (probe.stderr or "")
            dll_hint = _jlink_failure_hint(output)
            if dll_hint:
                all_ok &= _doctor_check(
                    "SEGGER J-Link runtime",
                    False,
                    detail=dll_hint.splitlines()[0],
                    hint="Run `JLinkExe` directly and reinstall SEGGER tools if the runtime is broken.",
                )
            else:
                all_ok &= _doctor_check(
                    "SEGGER J-Link runtime",
                    True,
                    detail="JLinkExe launched successfully.",
                )
        except subprocess.CalledProcessError as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            dll_hint = _jlink_failure_hint(output)
            if dll_hint:
                all_ok &= _doctor_check(
                    "SEGGER J-Link runtime",
                    False,
                    detail=dll_hint.splitlines()[0],
                    hint="Run `JLinkExe` directly and reinstall SEGGER tools if the runtime is broken.",
                )
            else:
                all_ok &= _doctor_check(
                    "SEGGER J-Link runtime",
                    True,
                    detail="JLinkExe launched. Probe connectivity was not required for this check.",
                )

    if not all_ok:
        raise SystemExit("One or more required tools are missing or misconfigured.")


def cmd_configure(args: argparse.Namespace) -> None:
    app_dir, _, _, _, board = _resolve_app_context(args)
    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else _default_build_dir(app_dir, board)
    )
    _run_cmake_configure(app_dir, build_dir, board)
    print(f"Configured app at: {app_dir}")
    print(f"Build directory: {build_dir}")


def cmd_build(args: argparse.Namespace) -> None:
    app_dir, _, _, app_name, board = _resolve_app_context(args)
    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else _default_build_dir(app_dir, board)
    )
    if not (build_dir / "build.ninja").exists():
        _run_cmake_configure(app_dir, build_dir, board)
    target = args.target or app_name
    _run(["cmake", "--build", str(build_dir), "--target", target, "-j", str(args.jobs)])


def cmd_flash(args: argparse.Namespace) -> None:
    app_dir, _, _, app_name, board = _resolve_app_context(args)
    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else _default_build_dir(app_dir, board)
    )
    if not (build_dir / "build.ninja").exists():
        _run_cmake_configure(app_dir, build_dir, board)
    target = f"{app_name}_flash"
    cmd = ["cmake", "--build", str(build_dir), "--target", target, "-j", str(args.jobs)]
    if VERBOSE > 0:
        _run(cmd)
        return
    try:
        result = _run_capture(cmd)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(_format_subprocess_error(exc, context="Flash")) from None
    _print_captured_output(result)


def cmd_view(args: argparse.Namespace) -> None:
    app_dir, _, _, app_name, board = _resolve_app_context(args)
    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else _default_build_dir(app_dir, board)
    )
    if not (build_dir / "build.ninja").exists():
        _run_cmake_configure(app_dir, build_dir, board)
    target = f"{app_name}_view"
    view_cmd = _extract_view_command(build_dir, target)
    try:
        subprocess.run(view_cmd, cwd=str(build_dir), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(_format_subprocess_error(exc, context="View")) from None


def cmd_clean(args: argparse.Namespace) -> None:
    app_dir, _, _, _, board = _resolve_app_context(args)
    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else _default_build_dir(app_dir, board)
    )
    if not build_dir.exists():
        return
    if args.full:
        shutil.rmtree(build_dir)
        print(f"Removed build directory: {build_dir}")
        return
    if not (build_dir / "build.ninja").exists():
        _run_cmake_configure(app_dir, build_dir, board)
    _run(["cmake", "--build", str(build_dir), "--target", "clean"])


def cmd_module_list(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)
    enabled = set(_module_names_from_nsx(nsx_cfg))
    _print_module_table(registry, enabled)


def cmd_module_add(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    workspace = _workspace_for_app_dir(app_dir)
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)

    enabled = _module_names_from_nsx(nsx_cfg)
    desired_modules = _unique_preserving_order(enabled + [args.module])
    _ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        desired_modules,
        sync=not args.no_sync,
    )
    new_modules = _resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    _ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        new_modules,
        sync=not args.no_sync,
    )
    if args.dry_run:
        print("[dry-run] modules to enable:", ", ".join(new_modules))
        return

    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _vendor_modules_into_app(app_dir, new_modules, registry, workspace)

    print(f"Enabled module '{args.module}'")
    print("Resolved module set:", ", ".join(new_modules))


def cmd_module_remove(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    workspace = _workspace_for_app_dir(app_dir)
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)
    enabled = _module_names_from_nsx(nsx_cfg)
    if args.module not in enabled:
        raise SystemExit(f"Module '{args.module}' is not enabled in nsx.yml")

    profile_name = nsx_cfg.get("profile")
    protected: set[str] = set()
    if isinstance(profile_name, str):
        profile = registry.get("starter_profiles", {}).get(profile_name, {})
        if isinstance(profile, dict):
            base_mods = profile.get("modules", [])
            if isinstance(base_mods, list):
                protected = {m for m in base_mods if isinstance(m, str)}

    current = set(enabled)
    remove_set = {args.module}
    dependents = _module_dependents(enabled, registry, workspace, app_dir=app_dir)

    blockers = sorted(name for name in dependents.get(args.module, set()) if name in current)
    if blockers:
        raise SystemExit(
            f"Cannot remove '{args.module}'; required by enabled module(s): {', '.join(blockers)}"
        )

    changed = True
    while changed:
        changed = False
        remaining = current - remove_set
        dependents = _module_dependents(sorted(remaining), registry, workspace, app_dir=app_dir)
        for mod in list(remaining):
            if mod in protected:
                continue
            if dependents.get(mod):
                continue
            metadata = _load_module_metadata(mod, registry, workspace, app_dir=app_dir)
            if metadata["module"]["type"] == "soc":
                continue
            remove_set.add(mod)
            changed = True

    desired_modules = [name for name in enabled if name not in remove_set]
    new_modules = _resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    if args.dry_run:
        print("[dry-run] modules to remove:", ", ".join(sorted(remove_set)))
        print("[dry-run] remaining modules:", ", ".join(new_modules))
        return

    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    for module_name in sorted(remove_set):
        _remove_vendored_module_from_app(app_dir, module_name, registry)

    print(f"Removed module '{args.module}'")
    print("Removed set:", ", ".join(sorted(remove_set)))
    print("Remaining modules:", ", ".join(new_modules))


def cmd_module_update(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    workspace = _workspace_for_app_dir(app_dir)
    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)

    current_modules = _module_names_from_nsx(nsx_cfg)
    current = set(current_modules)
    if args.module:
        if args.module not in current:
            raise SystemExit(f"Module '{args.module}' is not enabled in nsx.yml")
        to_update = {args.module}
    else:
        to_update = set(current)

    _ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        sorted(current),
        sync=not args.no_sync,
    )

    resolved_modules = _resolve_module_closure(
        current_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )

    if args.dry_run:
        print("[dry-run] modules to refresh from registry:", ", ".join(sorted(to_update)))
        return

    _update_nsx_cfg_modules(nsx_cfg, resolved_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    vendored_modules = [name for name in resolved_modules if name in to_update]
    _vendor_modules_into_app(app_dir, vendored_modules, registry, workspace)

    if args.module:
        print(f"Updated module '{args.module}' to lockfile revision")
    else:
        print("Updated all enabled modules to lockfile revisions")


def cmd_module_register(args: argparse.Namespace) -> None:
    app_dir = Path(args.app_dir).expanduser().resolve()
    workspace = _workspace_for_app_dir(app_dir)
    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)

    module_name = args.module
    metadata_path = Path(args.metadata).expanduser()
    if not metadata_path.is_absolute():
        metadata_path = (app_dir / metadata_path).resolve()
    if not metadata_path.exists():
        raise SystemExit(f"Metadata file does not exist: {metadata_path}")

    module_data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(module_data, str(metadata_path))
    declared_name = module_data.get("module", {}).get("name")
    if declared_name != module_name:
        raise SystemExit(
            f"Metadata module name mismatch: expected '{module_name}', "
            f"found '{declared_name}'"
        )

    manifest_projects = _manifest_projects_by_name(workspace)
    project_name = args.project
    existing_project = manifest_projects.get(project_name)
    project_entry: dict[str, Any] = {}
    if existing_project is not None:
        project_entry = {
            "name": project_name,
            "url": existing_project.get("url"),
            "revision": existing_project.get("revision"),
            "path": existing_project.get("path"),
        }
    else:
        if args.project_local_path and (
            args.project_url or args.project_revision or args.project_path
        ):
            raise SystemExit(
                "Use either --project-local-path OR (--project-url --project-revision --project-path), not both."
            )
        if args.project_local_path:
            local_path = Path(args.project_local_path).expanduser().resolve()
            if not local_path.exists():
                raise SystemExit(f"--project-local-path does not exist: {local_path}")
            project_entry = {
                "name": project_name,
                "local_path": str(local_path),
            }
        else:
            if not (args.project_url and args.project_revision and args.project_path):
                raise SystemExit(
                    f"Project '{project_name}' is not in workspace manifest. "
                    "Provide --project-local-path OR --project-url + --project-revision + --project-path."
                )
            project_entry = {
                "name": project_name,
                "url": args.project_url,
                "revision": args.project_revision,
                "path": args.project_path,
            }

    current_modules = registry.get("modules", {})
    if module_name in current_modules and not args.override:
        raise SystemExit(
            f"Module '{module_name}' already exists in effective registry. "
            "Use --override to replace it for this app."
        )

    target_cfg = copy.deepcopy(nsx_cfg)
    module_registry = target_cfg.setdefault("module_registry", {})
    if not isinstance(module_registry, dict):
        raise SystemExit("nsx.yml: module_registry must be a mapping")
    projects = module_registry.setdefault("projects", {})
    modules = module_registry.setdefault("modules", {})
    if not isinstance(projects, dict) or not isinstance(modules, dict):
        raise SystemExit("nsx.yml: module_registry.projects/modules must be mappings")

    projects[project_name] = project_entry
    modules[module_name] = {
        "project": project_name,
        "revision": project_entry.get("revision", "main"),
        "metadata": _metadata_storage_path(app_dir, metadata_path, project_entry),
    }

    if args.dry_run:
        print("[dry-run] would register module:")
        print(f"  module={module_name}")
        print(f"  project={project_name}")
        print(f"  metadata={modules[module_name]['metadata']}")
        return

    _save_app_cfg(app_dir, target_cfg)
    _write_app_module_file(app_dir, target_cfg)
    effective = _effective_registry(base_registry, target_cfg)
    _ensure_workspace_projects_for_modules(
        workspace,
        target_cfg,
        effective,
        [module_name],
        sync=not args.no_sync,
    )
    _vendor_modules_into_app(app_dir, [module_name], effective, workspace)

    print(f"Registered module '{module_name}' for app {app_dir.name}")
    print(f"Project: {project_name}")
    print(f"Metadata: {metadata_path}")


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
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        if VERBOSE > 0:
            raise
        raise SystemExit(_format_subprocess_error(exc, context="Command")) from None
    return 0
