"""Shared NSX workflow operations for CLI and programmatic use."""

from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .subprocess_utils import (
    extract_view_command,
    format_subprocess_error,
    jlink_failure_hint,
    print_captured_output,
    run,
    run_capture,
)
from .subprocess_utils import set_verbosity as set_subprocess_verbosity
from .tooling import doctor_check, require_tool, tool_cmd, tool_path

VERBOSE = 0


def set_verbosity(level: int) -> None:
    global VERBOSE
    VERBOSE = level
    set_subprocess_verbosity(level)


def _cli():
    from . import cli

    return cli


# Compatibility aliases for tests and incremental callers.
_run = run
_run_capture = run_capture
_print_captured_output = print_captured_output
_jlink_failure_hint = jlink_failure_hint
_tool_path = tool_path
_tool_cmd = tool_cmd
_require_tool = require_tool
_doctor_check = doctor_check
_extract_view_command = extract_view_command


def init_workspace_impl(
    workspace: Path,
    *,
    nsx_repo_url: str | None = None,
    nsx_revision: str = "main",
    ambiqsuite_repo_url: str | None = None,
    ambiqsuite_revision: str = "main",
    skip_update: bool = False,
) -> None:
    cli = _cli()
    _require_tool("west")

    manifest_dir = workspace / "manifest"
    west_yml = manifest_dir / "west.yml"

    workspace.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    default_nsx_url = cli._registry_project_entry(
        cli._load_registry(), cli.DEFAULT_REPO_NAME
    ).get("url")
    if not isinstance(default_nsx_url, str) or not default_nsx_url:
        raise SystemExit("Built-in registry is missing a default URL for the neuralspotx project.")
    effective_nsx_repo_url = nsx_repo_url or default_nsx_url

    manifest_text = cli._render_west_manifest(
        nsx_repo_url=effective_nsx_repo_url,
        nsx_revision=nsx_revision,
        ambiqsuite_url=ambiqsuite_repo_url,
        ambiqsuite_revision=ambiqsuite_revision,
    )
    west_yml.write_text(manifest_text, encoding="utf-8")

    if not (workspace / ".west").exists():
        _run(_tool_cmd("west", "init", "-l", "manifest"), cwd=workspace)

    if not skip_update:
        _run(_tool_cmd("west", "update"), cwd=workspace)

    print(f"NSX workspace initialized at: {workspace}")
    print(f"Root repo path in workspace: {workspace / cli.DEFAULT_REPO_NAME}")
    print(f"Manifest: {west_yml}")


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
    cli = _cli()
    base_registry = cli._load_registry()
    if init_workspace and not cli._workspace_has_manifest(workspace):
        cli.init_workspace_impl(
            workspace,
            skip_update=no_sync and no_bootstrap,
        )
    cli._require_initialized_workspace(workspace)

    soc = soc or cli.DEFAULT_SOC_FOR_BOARD.get(board)
    if soc is None:
        raise SystemExit(f"Unable to infer --soc for board '{board}'. Pass --soc explicitly.")

    template_root = cli.resources.files("neuralspotx.templates").joinpath("external_app")
    with cli.resources.as_file(template_root) as src_template:
        if not src_template.exists():
            raise SystemExit(f"Template directory not found: {src_template}")

        app_dir = workspace / "apps" / app_name
        if app_dir.exists() and any(app_dir.iterdir()) and not force:
            raise SystemExit(f"App directory already exists and is not empty: {app_dir}")

        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_template, app_dir, dirs_exist_ok=True)

    cli._copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")

    cmake_file = app_dir / "CMakeLists.txt"
    lines = cmake_file.read_text(encoding="utf-8").splitlines()
    lines = cli._replace_exact_line(
        lines,
        "project(__NSX_APP_NAME__ LANGUAGES C CXX ASM)",
        f"project({app_name} LANGUAGES C CXX ASM)",
    )
    lines = cli._replace_exact_line(
        lines, "add_executable(__NSX_APP_NAME__", f"add_executable({app_name}"
    )
    lines = cli._replace_exact_line(
        lines,
        "target_link_libraries(__NSX_APP_NAME__ PRIVATE",
        f"target_link_libraries({app_name} PRIVATE",
    )
    lines = cli._replace_exact_line(
        lines,
        "target_link_options(__NSX_APP_NAME__ PRIVATE",
        f"target_link_options({app_name} PRIVATE",
    )
    lines = cli._replace_exact_line(
        lines,
        "    target_link_libraries(__NSX_APP_NAME__ PRIVATE nsx::portable_api)",
        f"    target_link_libraries({app_name} PRIVATE nsx::portable_api)",
    )
    lines = cli._replace_exact_line(
        lines,
        "    add_custom_command(TARGET __NSX_APP_NAME__ POST_BUILD",
        f"    add_custom_command(TARGET {app_name} POST_BUILD",
    )
    lines = cli._replace_exact_line(
        lines,
        "        COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:__NSX_APP_NAME__> $<TARGET_FILE_DIR:__NSX_APP_NAME__>/__NSX_APP_NAME__.bin",
        f"        COMMAND ${{CMAKE_OBJCOPY}} -Obinary $<TARGET_FILE:{app_name}> $<TARGET_FILE_DIR:{app_name}>/{app_name}.bin",
    )
    lines = cli._replace_exact_line(
        lines,
        '        COMMENT "Generating __NSX_APP_NAME__.bin")',
        f'        COMMENT "Generating {app_name}.bin")',
    )
    lines = cli._replace_exact_line(
        lines,
        "        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:__NSX_APP_NAME__>",
        f"        COMMAND ${{CMAKE_SIZE}} $<TARGET_FILE:{app_name}>",
    )
    lines = cli._replace_exact_line(
        lines, "nsx_finalize_app(__NSX_APP_NAME__)", f"nsx_finalize_app({app_name})"
    )
    lines = cli._replace_exact_line(
        lines,
        "    -Wl,-Map,$<TARGET_FILE_DIR:__NSX_APP_NAME__>/__NSX_APP_NAME__.map",
        f"    -Wl,-Map,$<TARGET_FILE_DIR:{app_name}>/{app_name}.map",
    )
    lines = cli._replace_exact_line(
        lines,
        "find_package(nsx_soc_apollo510 REQUIRED CONFIG)",
        f"find_package(nsx_soc_{soc} REQUIRED CONFIG)",
    )
    lines = cli._replace_exact_line(
        lines,
        "find_package(nsx_board_apollo510_evb REQUIRED CONFIG)",
        f"find_package(nsx_board_{board} REQUIRED CONFIG)",
    )
    lines = cli._replace_exact_line(
        lines, "    nsx::board_apollo510_evb", f"    nsx::board_{board}"
    )

    if board != "apollo510_evb":
        lines = [line for line in lines if not line.startswith("set(NSX_SEGGER_")]

    cmake_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    nsx_cfg = cli._generate_nsx_config(
        app_name=app_name,
        board=board,
        soc=soc,
        registry=base_registry,
        west_manifest_rel="../../manifest/west.yml",
    )
    if no_bootstrap:
        nsx_cfg["modules"] = []
        cli._save_app_cfg(app_dir, nsx_cfg)
        cli._write_app_module_file(app_dir, nsx_cfg)
        print(f"Created app '{app_name}' at: {app_dir}")
        print("Starter modules were not bootstrapped (--no-bootstrap).")
        print("Next steps:")
        print(f"  1) cd {app_dir}")
        print("  2) Run `uv run nsx module list --app-dir .`")
        print("  3) Add modules with `uv run nsx module add <module> --app-dir .`")
        return app_dir

    registry = cli._effective_registry(base_registry, nsx_cfg)
    cli._ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        cli._module_names_from_nsx(nsx_cfg),
        sync=not no_sync,
    )
    starter_modules = cli._resolve_module_closure(
        cli._module_names_from_nsx(nsx_cfg),
        app_dir=None,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    cli._ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        starter_modules,
        sync=not no_sync,
    )
    cli._update_nsx_cfg_modules(nsx_cfg, starter_modules, registry)
    cli._save_app_cfg(app_dir, nsx_cfg)
    cli._write_app_module_file(app_dir, nsx_cfg)
    cli._vendor_modules_into_app(app_dir, starter_modules, registry, workspace)
    if nsx_cfg.get("profile_status") == "scaffold":
        print(
            f"NOTE: profile '{nsx_cfg.get('profile')}' is scaffold-only. "
            "Build bring-up may not be complete yet."
        )

    print(f"Created app '{app_name}' at: {app_dir}")
    print("Next steps:")
    print(f"  1) cd {app_dir}")
    print("  2) Run `uv run nsx configure --app-dir .`")
    print(
        "  3) Run `uv run nsx build --app-dir .`, `uv run nsx flash --app-dir .`, or `uv run nsx view --app-dir .`"
    )
    return app_dir


def sync_workspace_impl(workspace: Path) -> None:
    cli = _cli()
    _require_tool("west")
    cli._require_initialized_workspace(workspace)
    _run(_tool_cmd("west", "update"), cwd=workspace)


def doctor_impl() -> None:
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
        hint="Install `west`, or use an NSX install that provides it in the same environment.",
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
                _tool_cmd("JLinkExe", "-CommandFile", "-", "-NoGui", "1"),
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


def _resolve_build_context(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> tuple[Path, str, str, Path]:
    cli = _cli()
    resolved_app_dir, _, _, app_name, resolved_board = cli._resolve_app_context(
        argparse.Namespace(app_dir=str(app_dir), board=board)
    )
    resolved_build_dir = build_dir or cli._default_build_dir(resolved_app_dir, resolved_board)
    return resolved_app_dir, app_name, resolved_board, resolved_build_dir


def configure_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    cli = _cli()
    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    cli._run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    print(f"Configured app at: {resolved_app_dir}")
    print(f"Build directory: {resolved_build_dir}")
    return resolved_build_dir


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    target: str | None = None,
    jobs: int = 8,
) -> Path:
    cli = _cli()
    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        cli._run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    resolved_target = target or app_name
    _run(["cmake", "--build", str(resolved_build_dir), "--target", resolved_target, "-j", str(jobs)])
    return resolved_build_dir


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    jobs: int = 8,
) -> Path:
    cli = _cli()
    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        cli._run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    target = f"{app_name}_flash"
    cmd = ["cmake", "--build", str(resolved_build_dir), "--target", target, "-j", str(jobs)]
    if VERBOSE > 0:
        _run(cmd)
        return resolved_build_dir
    try:
        result = _run_capture(cmd)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(format_subprocess_error(exc, context="Flash")) from None
    _print_captured_output(result)
    return resolved_build_dir


def view_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> Path:
    cli = _cli()
    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        cli._run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    target = f"{app_name}_view"
    view_cmd = _extract_view_command(resolved_build_dir, target)
    try:
        subprocess.run(view_cmd, cwd=str(resolved_build_dir), check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(format_subprocess_error(exc, context="View")) from None
    return resolved_build_dir


def clean_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    full: bool = False,
) -> Path:
    cli = _cli()
    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not resolved_build_dir.exists():
        return resolved_build_dir
    if full:
        shutil.rmtree(resolved_build_dir)
        print(f"Removed build directory: {resolved_build_dir}")
        return resolved_build_dir
    if not (resolved_build_dir / "build.ninja").exists():
        cli._run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    _run(["cmake", "--build", str(resolved_build_dir), "--target", "clean"])
    return resolved_build_dir


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    cli = _cli()
    workspace = cli._workspace_for_app_dir(app_dir)
    nsx_cfg = cli._load_app_cfg(app_dir)
    registry = cli._effective_registry(cli._load_registry(), nsx_cfg)

    enabled = cli._module_names_from_nsx(nsx_cfg)
    desired_modules = cli._unique_preserving_order(enabled + [module_name])
    cli._ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        desired_modules,
        sync=not no_sync,
    )
    new_modules = cli._resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    cli._ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        new_modules,
        sync=not no_sync,
    )
    if dry_run:
        print("[dry-run] modules to enable:", ", ".join(new_modules))
        return new_modules

    cli._update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    cli._save_app_cfg(app_dir, nsx_cfg)
    cli._write_app_module_file(app_dir, nsx_cfg)
    cli._vendor_modules_into_app(app_dir, new_modules, registry, workspace)

    print(f"Enabled module '{module_name}'")
    print("Resolved module set:", ", ".join(new_modules))
    return new_modules


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
    no_sync: bool = False,
) -> tuple[list[str], list[str]]:
    cli = _cli()
    del no_sync
    workspace = cli._workspace_for_app_dir(app_dir)
    nsx_cfg = cli._load_app_cfg(app_dir)
    registry = cli._effective_registry(cli._load_registry(), nsx_cfg)
    enabled = cli._module_names_from_nsx(nsx_cfg)
    if module_name not in enabled:
        raise SystemExit(f"Module '{module_name}' is not enabled in nsx.yml")

    profile_name = nsx_cfg.get("profile")
    protected: set[str] = set()
    if isinstance(profile_name, str):
        profile = registry.get("starter_profiles", {}).get(profile_name, {})
        if isinstance(profile, dict):
            base_mods = profile.get("modules", [])
            if isinstance(base_mods, list):
                protected = {m for m in base_mods if isinstance(m, str)}

    current = set(enabled)
    remove_set = {module_name}
    dependents = cli._module_dependents(enabled, registry, workspace, app_dir=app_dir)

    blockers = sorted(name for name in dependents.get(module_name, set()) if name in current)
    if blockers:
        raise SystemExit(
            f"Cannot remove '{module_name}'; required by enabled module(s): {', '.join(blockers)}"
        )

    changed = True
    while changed:
        changed = False
        remaining = current - remove_set
        dependents = cli._module_dependents(sorted(remaining), registry, workspace, app_dir=app_dir)
        for mod in list(remaining):
            if mod in protected:
                continue
            if dependents.get(mod):
                continue
            metadata = cli._load_module_metadata(mod, registry, workspace, app_dir=app_dir)
            if metadata["module"]["type"] == "soc":
                continue
            remove_set.add(mod)
            changed = True

    desired_modules = [name for name in enabled if name not in remove_set]
    new_modules = cli._resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )
    if dry_run:
        print("[dry-run] modules to remove:", ", ".join(sorted(remove_set)))
        print("[dry-run] remaining modules:", ", ".join(new_modules))
        return sorted(remove_set), new_modules

    cli._update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    cli._save_app_cfg(app_dir, nsx_cfg)
    cli._write_app_module_file(app_dir, nsx_cfg)
    for removed_name in sorted(remove_set):
        cli._remove_vendored_module_from_app(app_dir, removed_name, registry)

    print(f"Removed module '{module_name}'")
    print("Removed set:", ", ".join(sorted(remove_set)))
    print("Remaining modules:", ", ".join(new_modules))
    return sorted(remove_set), new_modules


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
    no_sync: bool = False,
) -> list[str]:
    cli = _cli()
    workspace = cli._workspace_for_app_dir(app_dir)
    nsx_cfg = cli._load_app_cfg(app_dir)
    registry = cli._effective_registry(cli._load_registry(), nsx_cfg)

    current_modules = cli._module_names_from_nsx(nsx_cfg)
    current = set(current_modules)
    if module_name:
        if module_name not in current:
            raise SystemExit(f"Module '{module_name}' is not enabled in nsx.yml")
        to_update = {module_name}
    else:
        to_update = set(current)

    cli._ensure_workspace_projects_for_modules(
        workspace,
        nsx_cfg,
        registry,
        sorted(current),
        sync=not no_sync,
    )

    resolved_modules = cli._resolve_module_closure(
        current_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        workspace=workspace,
    )

    if dry_run:
        print("[dry-run] modules to refresh from registry:", ", ".join(sorted(to_update)))
        return sorted(to_update)

    cli._update_nsx_cfg_modules(nsx_cfg, resolved_modules, registry)
    cli._save_app_cfg(app_dir, nsx_cfg)
    cli._write_app_module_file(app_dir, nsx_cfg)
    vendored_modules = [name for name in resolved_modules if name in to_update]
    cli._vendor_modules_into_app(app_dir, vendored_modules, registry, workspace)

    if module_name:
        print(f"Updated module '{module_name}' to lockfile revision")
    else:
        print("Updated all enabled modules to lockfile revisions")
    return resolved_modules


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
    cli = _cli()
    workspace = cli._workspace_for_app_dir(app_dir)
    nsx_cfg = cli._load_app_cfg(app_dir)
    base_registry = cli._load_registry()
    registry = cli._effective_registry(base_registry, nsx_cfg)

    metadata_path = metadata
    if not metadata_path.is_absolute():
        metadata_path = (app_dir / metadata_path).resolve()
    if not metadata_path.exists():
        raise SystemExit(f"Metadata file does not exist: {metadata_path}")

    module_data = cli._read_yaml(metadata_path)
    cli.validate_nsx_module_metadata(module_data, str(metadata_path))
    declared_name = module_data.get("module", {}).get("name")
    if declared_name != module_name:
        raise SystemExit(
            f"Metadata module name mismatch: expected '{module_name}', found '{declared_name}'"
        )

    manifest_projects = cli._manifest_projects_by_name(workspace)
    project_name = project
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
        if project_local_path and (project_url or project_revision or project_path):
            raise SystemExit(
                "Use either --project-local-path OR (--project-url --project-revision --project-path), not both."
            )
        if project_local_path:
            local_path = project_local_path.resolve()
            if not local_path.exists():
                raise SystemExit(f"--project-local-path does not exist: {local_path}")
            project_entry = {
                "name": project_name,
                "local_path": str(local_path),
            }
        else:
            if not (project_url and project_revision and project_path):
                raise SystemExit(
                    f"Project '{project_name}' is not in workspace manifest. "
                    "Provide --project-local-path OR --project-url + --project-revision + --project-path."
                )
            project_entry = {
                "name": project_name,
                "url": project_url,
                "revision": project_revision,
                "path": project_path,
            }

    current_modules = registry.get("modules", {})
    if module_name in current_modules and not override:
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
        "metadata": cli._metadata_storage_path(app_dir, metadata_path, project_entry),
    }

    if dry_run:
        print("[dry-run] would register module:")
        print(f"  module={module_name}")
        print(f"  project={project_name}")
        print(f"  metadata={modules[module_name]['metadata']}")
        return metadata_path

    cli._save_app_cfg(app_dir, target_cfg)
    cli._write_app_module_file(app_dir, target_cfg)
    effective = cli._effective_registry(base_registry, target_cfg)
    cli._ensure_workspace_projects_for_modules(
        workspace,
        target_cfg,
        effective,
        [module_name],
        sync=not no_sync,
    )
    cli._vendor_modules_into_app(app_dir, [module_name], effective, workspace)

    print(f"Registered module '{module_name}' for app {app_dir.name}")
    print(f"Project: {project_name}")
    print(f"Metadata: {metadata_path}")
    return metadata_path
