"""Shared NSX workflow operations for CLI and programmatic use."""

from __future__ import annotations

import argparse
import copy
import importlib.resources as resources
import shutil
import subprocess
import time
from pathlib import Path

from .constants import (
    DEFAULT_SOC_FOR_BOARD,
    DEFAULT_TOOLCHAIN,
)
from .metadata import validate_nsx_module_metadata
from .models import ModuleEntry, ProjectEntry
from .module_registry import (
    _acquire_modules_for_app,
    _generate_nsx_config,
    _load_module_metadata,
    _local_module_names,
    _module_dependents,
    _module_names_from_nsx,
    _remove_vendored_module_from_app,
    _resolve_module_closure,
    _update_module_clone,
    _update_nsx_cfg_modules,
)
from .project_config import (
    _copy_packaged_tree,
    _default_build_dir,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _metadata_storage_path,
    _nsx_tool_major,
    _nsx_tool_version,
    _read_yaml,
    _registry_project_entry,
    _resolve_app_context,
    _run_cmake_configure,
    _save_app_cfg,
    _unique_preserving_order,
    _write_app_module_file,
    _write_modules_gitignore,
)
from .subprocess_utils import (
    extract_view_command,
    format_subprocess_error,
    jlink_failure_hint,
    print_captured_output,
    run,
    run_capture,
)
from .subprocess_utils import set_verbosity as set_subprocess_verbosity
from .templating import render_template_tree
from .tooling import doctor_check, require_tool, tool_cmd, tool_path

VERBOSE = 0


def set_verbosity(level: int) -> None:
    """Set shared operation verbosity for subprocess-facing helpers.

    Args:
        level: Verbosity level from the CLI or programmatic caller.
    """

    global VERBOSE
    VERBOSE = level
    set_subprocess_verbosity(level)


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


def create_app_impl(
    app_dir: Path,
    *,
    board: str = "apollo510_evb",
    soc: str | None = None,
    force: bool = False,
    no_bootstrap: bool = False,
) -> Path:
    """Create a new NSX app and clone its starter modules.

    Args:
        app_dir: App root directory to create.
        board: Target board identifier.
        soc: Optional SoC override.
        force: Allow writing into a non-empty app directory.
        no_bootstrap: Skip starter-module cloning.

    Returns:
        The created app directory.
    """

    base_registry = _load_registry()
    app_name = app_dir.name

    soc = soc or DEFAULT_SOC_FOR_BOARD.get(board)
    if soc is None:
        raise SystemExit(f"Unable to infer --soc for board '{board}'. Pass --soc explicitly.")

    template_root = resources.files("neuralspotx.templates").joinpath("external_app")
    with resources.as_file(template_root) as src_template:
        if not src_template.exists():
            raise SystemExit(f"Template directory not found: {src_template}")

        if app_dir.exists() and any(app_dir.iterdir()) and not force:
            raise SystemExit(f"App directory already exists and is not empty: {app_dir}")

        app_dir.mkdir(parents=True, exist_ok=True)
        render_template_tree(
            src_template,
            app_dir,
            context={
                "app_name": app_name,
                "board": board,
                "soc": soc,
            },
        )

    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")

    current_nsx_version = _nsx_tool_version()
    current_nsx_major = _nsx_tool_major(current_nsx_version)

    nsx_cfg = _generate_nsx_config(
        app_name=app_name,
        board=board,
        soc=soc,
        registry=base_registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
        nsx_version=current_nsx_version,
        nsx_major=current_nsx_major,
    )
    if no_bootstrap:
        nsx_cfg["modules"] = []
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        print(f"Created app '{app_name}' at: {app_dir}")
        print("Starter modules were not bootstrapped (--no-bootstrap).")
        print("Next steps:")
        print(f"  1) cd {app_dir}")
        print("  2) Run `nsx module list --app-dir .`")
        print("  3) Add modules with `nsx module add <module> --app-dir .`")
        return app_dir

    registry = _effective_registry(base_registry, nsx_cfg)

    # Pre-acquire seed modules so their nsx-module.yaml metadata is
    # available for dependency resolution below.
    seed_modules = _module_names_from_nsx(nsx_cfg)
    _acquire_modules_for_app(app_dir, seed_modules, registry)

    starter_modules = _resolve_module_closure(
        seed_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )
    _update_nsx_cfg_modules(nsx_cfg, starter_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    # Acquire any transitive dependencies discovered during resolution.
    _acquire_modules_for_app(app_dir, starter_modules, registry)
    _write_modules_gitignore(app_dir, nsx_cfg)
    if nsx_cfg.get("profile_status") == "scaffold":
        print(
            f"NOTE: profile '{nsx_cfg.get('profile')}' is scaffold-only. "
            "Build bring-up may not be complete yet."
        )

    print(f"Created app '{app_name}' at: {app_dir}")
    print("Next steps:")
    print(f"  1) cd {app_dir}")
    print("  2) Run `nsx configure --app-dir .`")
    print("  3) Run `nsx build --app-dir .`, `nsx flash --app-dir .`, or `nsx view --app-dir .`")
    return app_dir


def doctor_impl() -> None:
    """Run the NSX environment diagnostics and fail on missing prerequisites."""

    all_ok = True

    python_exe = shutil.which("python") or shutil.which("python3")
    all_ok &= _doctor_check("Python", python_exe is not None, detail=python_exe)
    all_ok &= _doctor_check("uv", _tool_path("uv") is not None, detail=_tool_path("uv"))
    all_ok &= _doctor_check("cmake", _tool_path("cmake") is not None, detail=_tool_path("cmake"))
    all_ok &= _doctor_check("ninja", _tool_path("ninja") is not None, detail=_tool_path("ninja"))
    all_ok &= _doctor_check(
        "git",
        _tool_path("git") is not None,
        detail=_tool_path("git"),
        hint="Install git.",
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


def _ensure_app_modules(app_dir: Path) -> None:
    """Ensure all modules declared in nsx.yml are present on disk.

    This is called during ``nsx configure`` so that a freshly-cloned app
    (whose registry modules are gitignored) can be configured without
    a separate ``nsx module add`` or ``nsx module update`` step.

    Only missing modules are acquired — existing vendored or cloned
    modules are left untouched.  Modules marked ``local: true`` are
    skipped entirely (they are source-controlled with the app).
    """

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)
    module_names = _module_names_from_nsx(nsx_cfg)
    local_names = _local_module_names(nsx_cfg)
    _acquire_modules_for_app(app_dir, module_names, registry, local_modules=local_names)
    # Re-copy packaged cmake tree in case it was gitignored, then
    # regenerate the app-specific modules.cmake that _copy_packaged_tree
    # would have removed (it does an rmtree before copying).
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)


def _resolve_build_context(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> tuple[Path, str, str, Path]:
    """Resolve the app, board, and build directory for a build-like action."""

    resolved_app_dir, _, app_name, resolved_board = _resolve_app_context(
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
    """Configure an app with CMake.

    Automatically acquires any missing modules (git clone or packaged
    copy) before running CMake so that a freshly cloned app whose
    ``modules/`` directory is gitignored works out of the box.

    Returns:
        The resolved build directory.
    """

    resolved_app_dir, _, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    _ensure_app_modules(resolved_app_dir)
    _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
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
    """Build an app target and return the build directory."""

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    resolved_target = target or app_name
    _run(
        ["cmake", "--build", str(resolved_build_dir), "--target", resolved_target, "-j", str(jobs)]
    )
    return resolved_build_dir


def flash_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    jobs: int = 8,
) -> Path:
    """Flash an app using its generated CMake flash target."""

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
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
    reset_on_open: bool = True,
    reset_delay_ms: int = 400,
) -> Path:
    """Launch the SEGGER SWO viewer for an app.

    By default, the viewer is attached first and then the target is reset once.
    This avoids a common race where SWO stays silent until the next reset.
    """

    resolved_app_dir, app_name, resolved_board, resolved_build_dir = _resolve_build_context(
        app_dir,
        board=board,
        build_dir=build_dir,
    )
    if not (resolved_build_dir / "build.ninja").exists():
        _ensure_app_modules(resolved_app_dir)
        _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    target = f"{app_name}_view"
    view_cmd = _extract_view_command(resolved_build_dir, target)
    viewer_proc: subprocess.Popen[bytes] | None = None
    try:
        viewer_proc = subprocess.Popen(view_cmd, cwd=str(resolved_build_dir))
        if reset_on_open:
            if reset_delay_ms > 0:
                time.sleep(reset_delay_ms / 1000.0)
            reset_cmd = [
                "cmake",
                "--build",
                str(resolved_build_dir),
                "--target",
                f"{app_name}_reset",
                "-j",
                "1",
            ]
            if VERBOSE > 0:
                _run(reset_cmd)
            else:
                try:
                    result = _run_capture(reset_cmd)
                except subprocess.CalledProcessError as exc:
                    if viewer_proc.poll() is None:
                        viewer_proc.terminate()
                        try:
                            viewer_proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            viewer_proc.kill()
                    raise SystemExit(format_subprocess_error(exc, context="Reset")) from None
                _print_captured_output(result)
        viewer_proc.wait()
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
    """Clean or fully remove an app build directory."""

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
        _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board)
    _run(["cmake", "--build", str(resolved_build_dir), "--target", "clean"])
    return resolved_build_dir


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    local: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Enable a module for an app and clone/copy the resolved closure.

    If *local* is True the module is marked ``local: true`` in nsx.yml.
    Local modules live inside the app tree (``modules/<name>/``), are
    source-controlled with the app, and are not acquired from a registry
    or git remote.
    """

    nsx_cfg = _load_app_cfg(app_dir)

    if local:
        # Local modules bypass registry resolution entirely.
        existing = _module_names_from_nsx(nsx_cfg)
        if module_name in existing:
            raise SystemExit(f"Module '{module_name}' is already enabled in nsx.yml")
        if dry_run:
            print(f"[dry-run] would add local module: {module_name}")
            return existing + [module_name]
        modules_list = nsx_cfg.setdefault("modules", [])
        modules_list.append({"name": module_name, "local": True})
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        print(f"Registered local module '{module_name}'")
        print("The module directory should be at: modules/" + module_name + "/")
        return _module_names_from_nsx(nsx_cfg)

    registry = _effective_registry(_load_registry(), nsx_cfg)

    enabled = _module_names_from_nsx(nsx_cfg)
    desired_modules = _unique_preserving_order(enabled + [module_name])
    new_modules = _resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )
    if dry_run:
        print("[dry-run] modules to enable:", ", ".join(new_modules))
        return new_modules

    local_names = _local_module_names(nsx_cfg)
    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _acquire_modules_for_app(app_dir, new_modules, registry, local_modules=local_names)
    _write_modules_gitignore(app_dir, nsx_cfg)

    print(f"Enabled module '{module_name}'")
    print("Resolved module set:", ", ".join(new_modules))
    return new_modules


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
) -> tuple[list[str], list[str]]:
    """Remove a module and any no-longer-needed dependents from an app."""

    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)
    enabled = _module_names_from_nsx(nsx_cfg)
    if module_name not in enabled:
        raise SystemExit(f"Module '{module_name}' is not enabled in nsx.yml")

    local_names = _local_module_names(nsx_cfg)

    # Local modules are simply removed from nsx.yml — their on-disk
    # directory is left untouched since it is source-controlled.
    if module_name in local_names:
        if dry_run:
            print(f"[dry-run] would remove local module: {module_name}")
            remaining = [n for n in enabled if n != module_name]
            return [module_name], remaining
        nsx_cfg["modules"] = [
            m
            for m in nsx_cfg.get("modules", [])
            if not (isinstance(m, dict) and m.get("name") == module_name)
        ]
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        remaining = _module_names_from_nsx(nsx_cfg)
        print(f"Removed local module '{module_name}' from nsx.yml")
        print("(Module directory was NOT deleted — remove it manually if desired.)")
        return [module_name], remaining

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
    dependents = _module_dependents(enabled, registry, app_dir=app_dir, local_modules=local_names)

    blockers = sorted(name for name in dependents.get(module_name, set()) if name in current)
    if blockers:
        raise SystemExit(
            f"Cannot remove '{module_name}'; required by enabled module(s): {', '.join(blockers)}"
        )

    changed = True
    while changed:
        changed = False
        remaining = current - remove_set
        dependents = _module_dependents(
            sorted(remaining), registry, app_dir=app_dir, local_modules=local_names
        )
        for mod in list(remaining):
            if mod in protected:
                continue
            if mod in local_names:
                continue
            if dependents.get(mod):
                continue
            metadata = _load_module_metadata(mod, registry, app_dir=app_dir)
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
        default_toolchain=DEFAULT_TOOLCHAIN,
    )
    if dry_run:
        print("[dry-run] modules to remove:", ", ".join(sorted(remove_set)))
        print("[dry-run] remaining modules:", ", ".join(new_modules))
        return sorted(remove_set), new_modules

    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)
    for removed_name in sorted(remove_set):
        _remove_vendored_module_from_app(app_dir, removed_name, registry)

    print(f"Removed module '{module_name}'")
    print("Removed set:", ", ".join(sorted(remove_set)))
    print("Remaining modules:", ", ".join(new_modules))
    return sorted(remove_set), new_modules


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Refresh enabled modules to the current registry revisions."""

    nsx_cfg = _load_app_cfg(app_dir)
    registry = _effective_registry(_load_registry(), nsx_cfg)

    local_names = _local_module_names(nsx_cfg)
    current_modules = _module_names_from_nsx(nsx_cfg)
    current = set(current_modules)
    if module_name:
        if module_name not in current:
            raise SystemExit(f"Module '{module_name}' is not enabled in nsx.yml")
        if module_name in local_names:
            raise SystemExit(
                f"Module '{module_name}' is a local module and cannot be updated from registry"
            )
        to_update = {module_name}
    else:
        to_update = current - local_names

    resolved_modules = _resolve_module_closure(
        current_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )

    if dry_run:
        print("[dry-run] modules to refresh from registry:", ", ".join(sorted(to_update)))
        return sorted(to_update)

    _update_nsx_cfg_modules(nsx_cfg, resolved_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    for name in resolved_modules:
        if name in to_update:
            _update_module_clone(app_dir, name, registry)

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
) -> Path:
    """Register an app-local module override and acquire it into the app."""

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)

    metadata_path = metadata
    if not metadata_path.is_absolute():
        metadata_path = (app_dir / metadata_path).resolve()
    if not metadata_path.exists():
        raise SystemExit(f"Metadata file does not exist: {metadata_path}")

    module_data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(module_data, str(metadata_path))
    declared_name = module_data.get("module", {}).get("name")
    if declared_name != module_name:
        raise SystemExit(
            f"Metadata module name mismatch: expected '{module_name}', found '{declared_name}'"
        )

    project_name = project
    project_entry: ProjectEntry
    if project_local_path and (project_url or project_revision or project_path):
        raise SystemExit(
            "Use either --project-local-path OR (--project-url --project-revision --project-path), not both."
        )
    if project_local_path:
        local_path = project_local_path.resolve()
        if not local_path.exists():
            raise SystemExit(f"--project-local-path does not exist: {local_path}")
        project_entry = ProjectEntry(
            name=project_name,
            local_path=str(local_path),
            path=f"modules/{module_name}",
        )
    elif project_url:
        project_entry = ProjectEntry(
            name=project_name,
            url=project_url,
            revision=project_revision or "main",
            path=project_path or f"modules/{project_name}",
        )
    else:
        # Check if project already exists in registry
        existing = _registry_project_entry(registry, project_name)
        if existing.url:
            project_entry = existing
        else:
            raise SystemExit(
                f"Project '{project_name}' is not in registry. "
                "Provide --project-local-path OR --project-url."
            )

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

    projects[project_name] = project_entry.to_mapping()
    modules[module_name] = ModuleEntry(
        name=module_name,
        project=project_name,
        revision=project_entry.revision or "main",
        metadata=_metadata_storage_path(app_dir, metadata_path, project_entry),
    ).to_mapping()

    if dry_run:
        print("[dry-run] would register module:")
        print(f"  module={module_name}")
        print(f"  project={project_name}")
        print(f"  metadata={modules[module_name]['metadata']}")
        return metadata_path

    _save_app_cfg(app_dir, target_cfg)
    _write_app_module_file(app_dir, target_cfg)
    effective = _effective_registry(base_registry, target_cfg)
    _acquire_modules_for_app(app_dir, [module_name], effective)
    _write_modules_gitignore(app_dir, target_cfg)

    print(f"Registered module '{module_name}' for app {app_dir.name}")
    print(f"Project: {project_name}")
    print(f"Metadata: {metadata_path}")
    return metadata_path
