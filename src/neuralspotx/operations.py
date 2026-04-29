"""Shared NSX workflow operations for CLI and programmatic use."""

from __future__ import annotations

import argparse
import copy
import importlib.resources as resources
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .constants import (
    DEFAULT_SOC_FOR_BOARD,
    DEFAULT_TOOLCHAIN,
)
from .metadata import load_yaml, validate_nsx_module_metadata
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
    _vendored_module_names,
)
from .nsx_lock import (
    NsxLock,
    ResolutionError,
    ResolvedModule,
    hash_manifest,
    hash_tree,
    lock_path,
    read_lock,
    resolve_commit,
    resolve_ref,
    utcnow_iso,
    write_lock,
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
from .tooling import (
    JLINK_NAMES,
    JLINK_SWO_NAMES,
    doctor_check,
    find_segger_tool,
    require_tool,
    tool_cmd,
    tool_path,
)

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


def _module_package_name(module_name: str) -> str:
    """Convert a module name into its default CMake package/header stem."""

    return module_name.replace("-", "_")


def _module_target_name(module_name: str) -> str:
    """Convert a module name into its default namespaced CMake target."""

    stem = _module_package_name(module_name)
    if stem.startswith("nsx_"):
        stem = stem[4:]
    return f"nsx::{stem}"


def init_module_impl(
    module_dir: Path,
    *,
    module_name: str | None = None,
    module_type: str = "runtime",
    summary: str | None = None,
    version: str = "0.1.0",
    dependencies: list[str] | None = None,
    boards: list[str] | None = None,
    socs: list[str] | None = None,
    toolchains: list[str] | None = None,
    force: bool = False,
) -> Path:
    """Create a standard custom-module skeleton."""

    module_name = (module_name or module_dir.name).strip()
    if not module_name:
        raise SystemExit("Module name must not be empty.")

    if module_dir.exists() and not module_dir.is_dir():
        raise SystemExit(f"Module path already exists and is not a directory: {module_dir}")
    if module_dir.exists() and any(module_dir.iterdir()) and not force:
        raise SystemExit(f"Module directory already exists and is not empty: {module_dir}")

    dependency_names = _unique_preserving_order(dependencies or [])
    board_names = _unique_preserving_order(boards or ["*"])
    soc_names = _unique_preserving_order(socs or ["*"])
    toolchain_names = _unique_preserving_order(toolchains or [DEFAULT_TOOLCHAIN])

    package_name = _module_package_name(module_name)
    module_target = _module_target_name(module_name)
    summary_text = summary or f"TODO: describe what {module_name} provides."
    dependency_records = [
        {
            "name": dep,
            "package": _module_package_name(dep),
            "target": _module_target_name(dep),
        }
        for dep in dependency_names
    ]

    template_root = resources.files("neuralspotx.templates").joinpath("module_skeleton")
    with resources.as_file(template_root) as src_template:
        if not src_template.exists():
            raise SystemExit(f"Template directory not found: {src_template}")

        module_dir.mkdir(parents=True, exist_ok=True)
        render_template_tree(
            src_template,
            module_dir,
            context={
                "module_name": module_name,
                "module_type": module_type,
                "version": version,
                "summary_literal": json.dumps(summary_text),
                "package_name": package_name,
                "module_target": module_target,
                "include_dir": package_name,
                "include_guard": f"{package_name.upper()}_H",
                "dependency_names": dependency_names,
                "dependency_records": dependency_records,
                "boards": board_names,
                "socs": soc_names,
                "toolchains": toolchain_names,
            },
        )

    metadata_path = module_dir / "nsx-module.yaml"
    validate_nsx_module_metadata(load_yaml(metadata_path), str(metadata_path))

    print(f"Created module skeleton '{module_name}' at: {module_dir}")
    print("Next steps:")
    print("  1) Review nsx-module.yaml and fill in summary, capabilities, and compatibility")
    print(f"  2) Run `nsx module validate {metadata_path}`")
    print(
        "  3) Register it into an app with `nsx module register "
        f"{module_name} --metadata {metadata_path} --project {package_name} "
        f"--project-local-path {module_dir} --app-dir <app-dir>`"
    )
    return module_dir


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

    # armclang is optional — report but do not fail doctor when missing.
    armclang_path = _tool_path("armclang")
    armlink_path = _tool_path("armlink")
    fromelf_path = _tool_path("fromelf")
    if armclang_path or armlink_path or fromelf_path:
        _doctor_check(
            "armclang",
            armclang_path is not None,
            detail=armclang_path,
            hint="Install Arm Compiler for Embedded (armclang) if you want the armclang toolchain.",
        )
        _doctor_check(
            "armlink",
            armlink_path is not None,
            detail=armlink_path,
            hint="armlink should ship alongside armclang.",
        )
        _doctor_check(
            "fromelf",
            fromelf_path is not None,
            detail=fromelf_path,
            hint="fromelf should ship alongside armclang.",
        )
    else:
        print("  (armclang toolchain not detected — optional)")

    # ATfE (Arm Toolchain for Embedded) — optional.
    # ATFE_ROOT env var points to the install dir; tools are NOT on PATH.
    atfe_root = os.environ.get("ATFE_ROOT", "")
    if atfe_root:
        atfe_bin = os.path.join(atfe_root, "bin")
        atfe_clang = (
            os.path.join(atfe_bin, "clang")
            if os.path.isfile(os.path.join(atfe_bin, "clang"))
            else None
        )
        atfe_objcopy = (
            os.path.join(atfe_bin, "llvm-objcopy")
            if os.path.isfile(os.path.join(atfe_bin, "llvm-objcopy"))
            else None
        )
        atfe_newlib_cfg = (
            os.path.join(atfe_bin, "newlib.cfg")
            if os.path.isfile(os.path.join(atfe_bin, "newlib.cfg"))
            else None
        )
        _doctor_check(
            "ATfE clang",
            atfe_clang is not None,
            detail=atfe_clang,
            hint="ATFE_ROOT is set but clang not found in $ATFE_ROOT/bin.",
        )
        _doctor_check(
            "ATfE llvm-objcopy",
            atfe_objcopy is not None,
            detail=atfe_objcopy,
            hint="llvm-objcopy should ship alongside ATfE clang.",
        )
        _doctor_check(
            "ATfE newlib.cfg",
            atfe_newlib_cfg is not None,
            detail=atfe_newlib_cfg,
            hint="Install the ATfE newlib overlay — extract ATfE-newlib-overlay on top of the ATfE install.",
        )
    else:
        print("  (ATfE toolchain not detected — set ATFE_ROOT to enable; optional)")

    jlink_path = find_segger_tool(JLINK_NAMES)
    jlink_ok = jlink_path is not None
    all_ok &= _doctor_check(
        "SEGGER J-Link",
        jlink_ok,
        detail=jlink_path,
        hint="Install the SEGGER J-Link package and ensure JLinkExe (Linux/macOS) or JLink (Windows) is in PATH.",
    )

    swo_path = find_segger_tool(JLINK_SWO_NAMES)
    all_ok &= _doctor_check(
        "SEGGER JLinkSWOViewerCL",
        swo_path is not None,
        detail=swo_path,
        hint="Install the SEGGER J-Link package and ensure JLinkSWOViewerCL is in PATH.",
    )

    if jlink_ok:
        try:
            probe = subprocess.run(
                [jlink_path, "-CommandFile", "-", "-NoGui", "1"],
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


def _scaffold_vendored_module(target_dir: Path, module_name: str) -> None:
    """Drop minimal ``nsx-module.yaml`` + ``CMakeLists.txt`` into *target_dir*.

    Existing files are left untouched so the helper is idempotent and
    safe to run on a partially-populated module directory.
    """

    metadata_path = target_dir / "nsx-module.yaml"
    if not metadata_path.exists():
        metadata_path.write_text(
            "schema_version: 1\n"
            "module:\n"
            f"  name: {module_name}\n"
            "  type: app\n"
            f'  description: "Vendored module {module_name}"\n'
            "support:\n"
            "  ambiqsuite: true\n"
            "compatibility:\n"
            '  boards: ["*"]\n'
            '  socs: ["*"]\n'
            '  toolchains: ["*"]\n'
            "depends:\n"
            "  required: []\n",
            encoding="utf-8",
        )
    cmake_path = target_dir / "CMakeLists.txt"
    if not cmake_path.exists():
        cmake_path.write_text(
            f"# {module_name} — vendored module (committed in this app).\n"
            f"# Add sources / link libraries below; re-run `nsx lock` after edits.\n"
            f"add_library({module_name} INTERFACE)\n"
            f"target_include_directories({module_name} INTERFACE ${{CMAKE_CURRENT_SOURCE_DIR}})\n",
            encoding="utf-8",
        )


def _ensure_app_modules(app_dir: Path) -> None:
    """Ensure all modules declared in nsx.yml are present on disk.

    This is called during ``nsx configure`` so that a freshly-cloned app
    (whose registry modules are gitignored) can be configured without
    a separate ``nsx module add`` or ``nsx module update`` step.

    When an ``nsx.lock`` is present it is used as the source of truth
    (delegates to :func:`sync_app_impl`). Otherwise the legacy "clone
    each module at its branch tip" path is used and a warning printed
    so the user knows to run ``nsx lock``.

    Modules marked ``local: true`` are skipped entirely (they are
    source-controlled with the app).
    """

    if (app_dir / "nsx.lock").exists():
        sync_app_impl(app_dir)
        return

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)
    module_names = _module_names_from_nsx(nsx_cfg)
    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    _acquire_modules_for_app(
        app_dir,
        module_names,
        registry,
        local_modules=local_names,
        vendored_modules=vendored_names,
    )
    # Re-copy packaged cmake tree in case it was gitignored, then
    # regenerate the app-specific modules.cmake that _copy_packaged_tree
    # would have removed (it does an rmtree before copying).
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)
    print(
        "note: nsx.lock not found; modules acquired at branch tip. "
        "Run `nsx lock` to record reproducible commits."
    )


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
    toolchain: str | None = None,
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
    _run_cmake_configure(resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain)
    print(f"Configured app at: {resolved_app_dir}")
    print(f"Build directory: {resolved_build_dir}")
    return resolved_build_dir


def build_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
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
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
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
    toolchain: str | None = None,
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
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
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
    toolchain: str | None = None,
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
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
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
    toolchain: str | None = None,
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
        _run_cmake_configure(
            resolved_app_dir, resolved_build_dir, resolved_board, toolchain=toolchain
        )
    _run(["cmake", "--build", str(resolved_build_dir), "--target", "clean"])
    return resolved_build_dir


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    local: bool = False,
    vendored: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Enable a module for an app and clone/copy the resolved closure.

    Args:
        local: Mark as ``local: true`` in nsx.yml. Module lives inside
            the app tree (``modules/<name>/``), is mirrored from an
            external path, and is gitignored.
        vendored: Mark with ``source: { vendored: true }`` in nsx.yml.
            Module lives inside the app tree (``modules/<name>/``), is
            committed in the app's git, and is never touched by ``nsx
            sync``. A minimal ``nsx-module.yaml`` and ``CMakeLists.txt``
            are scaffolded if absent.
    """

    if local and vendored:
        raise SystemExit("--local and --vendored are mutually exclusive")

    nsx_cfg = _load_app_cfg(app_dir)

    if vendored:
        existing = _module_names_from_nsx(nsx_cfg)
        if module_name in existing:
            raise SystemExit(f"Module '{module_name}' is already enabled in nsx.yml")
        target_dir = app_dir / "modules" / module_name
        if dry_run:
            print(f"[dry-run] would scaffold vendored module: {module_name}")
            print(f"[dry-run]   directory: {target_dir.relative_to(app_dir)}/")
            print(f"[dry-run]   nsx.yml:  - name: {module_name}\\n    source: {{ vendored: true }}")
            return existing + [module_name]
        target_dir.mkdir(parents=True, exist_ok=True)
        _scaffold_vendored_module(target_dir, module_name)
        modules_list = nsx_cfg.setdefault("modules", [])
        modules_list.append({"name": module_name, "source": {"vendored": True}})
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        # Refresh the lock so the new module's content_hash is recorded.
        if (app_dir / "nsx.lock").exists():
            lock_app_impl(app_dir)
        print(f"Registered vendored module '{module_name}'")
        print(f"  scaffolded: {target_dir.relative_to(app_dir)}/")
        print(f"  next: edit {target_dir.relative_to(app_dir)}/CMakeLists.txt and run `nsx lock`")
        return _module_names_from_nsx(nsx_cfg)

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


# ---------------------------------------------------------------------------
# nsx.lock — resolution receipt and sync
# ---------------------------------------------------------------------------


def _resolved_module_path(
    app_dir: Path,
    module_name: str,
    registry: dict,
) -> Path:
    """Return the on-disk vendored directory for *module_name* in *app_dir*."""

    from .metadata import registry_entry_for_module
    from .module_registry import _is_packaged_module
    from .project_config import _module_clone_dir, _vendored_target_dir

    entry = registry_entry_for_module(registry, module_name)
    if _is_packaged_module(registry, module_name):
        return _vendored_target_dir(app_dir, module_name, entry.metadata)
    return _module_clone_dir(app_dir, entry.project, registry)


def _build_lock_for_app(
    app_dir: Path,
    *,
    previous: NsxLock | None = None,
) -> NsxLock:
    """Resolve every module in nsx.yml to a commit + content hash.

    Re-uses entries from *previous* (the existing lock) when the
    constraint is unchanged AND a vendored copy is already on disk with
    a matching content hash — avoids redundant ``git ls-remote`` calls.
    """

    from .metadata import registry_entry_for_module
    from .module_registry import _is_packaged_module

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)
    module_names = _module_names_from_nsx(nsx_cfg)
    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    tool_version = _nsx_tool_version()

    # Regenerate the deterministic side-effects that ``nsx sync`` produces
    # at the end of every run, so the hashes recorded here reflect the
    # post-sync state. Without this, editing nsx.yml and running ``nsx
    # lock`` before ``nsx sync`` would record a stale ``cmake/nsx/
    # modules.cmake`` content hash and trip ``--frozen`` on the next sync.
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)

    lock = NsxLock(
        generated_at=utcnow_iso(),
        nsx_tool_version=tool_version,
        manifest_path="nsx.yml",
        manifest_hash=hash_manifest(app_dir / "nsx.yml"),
        target={
            **(nsx_cfg.get("target") or {}),
            "toolchain": str(nsx_cfg.get("toolchain") or DEFAULT_TOOLCHAIN),
        },
    )

    prev_modules = previous.modules if previous else {}

    for name in module_names:
        # Vendored (in-app, source-controlled) modules — record content hash
        # only; no registry, no upstream resolution. The user owns these.
        if name in vendored_names:
            vendored_dir = app_dir / "modules" / name
            if not vendored_dir.exists():
                raise SystemExit(
                    f"Module '{name}' declares source: {{ vendored: true }} "
                    f"but {vendored_dir.relative_to(app_dir)}/ is missing. "
                    "Add the module's files (e.g. via `nsx module add --vendored`) "
                    "and re-run `nsx lock`."
                )
            rel = str(vendored_dir.relative_to(app_dir))
            constraint_str = "vendored"
            project_key = name  # vendored modules don't belong to a registry project
            for item in nsx_cfg.get("modules", []):
                if isinstance(item, dict) and item.get("name") == name:
                    if isinstance(item.get("project"), str):
                        project_key = item["project"]
                    break
            lock.modules[name] = ResolvedModule(
                project=project_key,
                kind="vendored",
                constraint=constraint_str,
                vendored_at=rel,
                content_hash=hash_tree(vendored_dir),
                acquired_at=utcnow_iso(),
            )
            continue

        # Local modules are source-controlled with the app — record only
        # the on-disk content hash; no upstream resolution. Handle these
        # BEFORE the registry lookup, since `nsx module add --local` may
        # have written `local: true` without a corresponding registry
        # override (regular registry-backed locals fall through to the
        # full `entry`-driven path).
        if name in local_names:
            try:
                entry = registry_entry_for_module(registry, name)
                project_key = entry.project
                constraint = str(entry.revision or "local")
                vendored_dir = _resolved_module_path(app_dir, name, registry)
            except ValueError:
                # No registry entry: hash modules/<name>/ directly.
                project_key = name
                constraint = "local"
                vendored_dir = app_dir / "modules" / name
            rel = (
                str(vendored_dir.relative_to(app_dir))
                if vendored_dir.is_relative_to(app_dir)
                else str(vendored_dir)
            )
            lock.modules[name] = ResolvedModule(
                project=project_key,
                kind="local",
                constraint=constraint,
                vendored_at=rel,
                content_hash=hash_tree(vendored_dir),
                acquired_at=utcnow_iso(),
            )
            continue

        entry = registry_entry_for_module(registry, name)
        constraint = str(entry.revision or "main")

        if _is_packaged_module(registry, name):
            vendored_dir = _resolved_module_path(app_dir, name, registry)
            rel = (
                str(vendored_dir.relative_to(app_dir))
                if vendored_dir.is_relative_to(app_dir)
                else str(vendored_dir)
            )
            lock.modules[name] = ResolvedModule(
                project=entry.project,
                kind="packaged",
                constraint="packaged",
                vendored_at=rel,
                content_hash=hash_tree(vendored_dir),
                acquired_at=utcnow_iso(),
                tool_version=tool_version,
            )
            continue

        # Git-hosted module — resolve constraint to a commit SHA via ls-remote.
        project_entry = _registry_project_entry(registry, entry.project)
        url = project_entry.url
        if not url:
            raise SystemExit(
                f"Module '{name}' project '{entry.project}' has no URL in registry; cannot lock."
            )

        previous_entry = prev_modules.get(name)
        commit: str | None
        tag: str | None
        if (
            previous_entry
            and previous_entry.kind == "git"
            and previous_entry.constraint == constraint
            and previous_entry.url == url
            and previous_entry.commit
        ):
            # Re-use the previously resolved SHA — `nsx update` is the
            # explicit way to re-resolve.
            commit = previous_entry.commit
            tag = previous_entry.tag
        else:
            try:
                commit, matched = resolve_ref(url, constraint)
            except ResolutionError as exc:
                # Upstream not reachable yet (e.g. repo not published). Degrade
                # to a content-only lock — sync will verify hash but won't
                # attempt to re-clone.
                print(
                    f"warning: could not resolve {name} @ {constraint} "
                    f"on {url} ({exc}); recording content-only lock entry."
                )
                vendored_dir = _resolved_module_path(app_dir, name, registry)
                rel = (
                    str(vendored_dir.relative_to(app_dir))
                    if vendored_dir.is_relative_to(app_dir)
                    else str(vendored_dir)
                )
                lock.modules[name] = ResolvedModule(
                    project=entry.project,
                    kind="unresolved",
                    constraint=constraint,
                    vendored_at=rel,
                    content_hash=hash_tree(vendored_dir),
                    acquired_at=utcnow_iso(),
                    url=url,
                    tag=None,
                    commit=None,
                )
                continue
            tag = constraint if matched == "tag" else None

        vendored_dir = _resolved_module_path(app_dir, name, registry)
        rel = (
            str(vendored_dir.relative_to(app_dir))
            if vendored_dir.is_relative_to(app_dir)
            else str(vendored_dir)
        )
        lock.modules[name] = ResolvedModule(
            project=entry.project,
            kind="git",
            constraint=constraint,
            vendored_at=rel,
            content_hash=hash_tree(vendored_dir),
            acquired_at=utcnow_iso(),
            url=url,
            tag=tag,
            commit=commit,
        )

    return lock


def lock_app_impl(
    app_dir: Path,
    *,
    update: bool = False,
    modules: list[str] | None = None,
    check: bool = False,
) -> Path:
    """Resolve and write ``nsx.lock`` for *app_dir*.

    Args:
        update: When True, re-resolve every module's constraint to its
            current upstream HEAD/tag (equivalent to ``nsx update``).
        modules: When given alongside ``update``, only re-resolve these.
        check: Read-only mode. Resolve as usual but, instead of writing,
            compare against the on-disk ``nsx.lock`` and raise
            ``SystemExit`` (with a non-zero status) when they would
            differ. Useful in CI to assert that ``nsx.lock`` is up to
            date with ``nsx.yml``.

    Returns:
        The path to the (would-be) ``nsx.lock``.
    """

    previous = read_lock(app_dir, allow_legacy=True)
    on_disk_lock = previous  # capture before update-mutation

    if update:
        if previous and modules:
            # Drop the named entries from `previous` so they get re-resolved.
            kept = {n: e for n, e in previous.modules.items() if n not in set(modules)}
            previous = NsxLock(
                schema_version=previous.schema_version,
                generated_at=previous.generated_at,
                nsx_tool_version=previous.nsx_tool_version,
                manifest_path=previous.manifest_path,
                manifest_hash=previous.manifest_hash,
                target=previous.target,
                modules=kept,
            )
        elif previous and not modules:
            previous = None  # full refresh

    lock = _build_lock_for_app(app_dir, previous=previous)
    lock_file = lock_path(app_dir)

    if check:
        diff = _diff_locks(on_disk_lock, lock)
        rel = (
            lock_file.relative_to(app_dir.parent)
            if lock_file.is_relative_to(app_dir.parent)
            else lock_file
        )
        if not diff:
            print(f"{rel} is up to date.")
            return lock_file
        print(f"{rel} is OUT OF DATE:")
        for line in diff:
            print(f"  {line}")
        print("Run `nsx lock` to refresh.")
        raise SystemExit(1)

    path = write_lock(app_dir, lock)
    print(
        f"Wrote {path.relative_to(app_dir.parent) if path.is_relative_to(app_dir.parent) else path}"
    )
    n_git = sum(1 for m in lock.modules.values() if m.kind == "git")
    n_pkg = sum(1 for m in lock.modules.values() if m.kind == "packaged")
    n_loc = sum(1 for m in lock.modules.values() if m.kind == "local")
    n_ven = sum(1 for m in lock.modules.values() if m.kind == "vendored")
    n_unres = sum(1 for m in lock.modules.values() if m.kind == "unresolved")
    parts = [f"{n_git} git", f"{n_pkg} packaged", f"{n_loc} local"]
    if n_ven:
        parts.append(f"{n_ven} vendored")
    if n_unres:
        parts.append(f"{n_unres} unresolved (upstream unreachable)")
    print(f"  modules: {len(lock.modules)} ({', '.join(parts)})")
    return path


def _diff_locks(previous: NsxLock | None, fresh: NsxLock) -> list[str]:
    """Return a human-readable list of differences relevant to drift detection.

    Compares only the resolution-affecting fields (manifest hash, kind,
    constraint, commit, content_hash) — not timestamps or the tool
    version, which legitimately move on every regenerate.
    """

    if previous is None:
        return [f"no nsx.lock present (would create {len(fresh.modules)} entries)"]

    diffs: list[str] = []
    if previous.manifest_hash != fresh.manifest_hash:
        diffs.append(
            f"manifest hash: {previous.manifest_hash[:14]}\u2026 -> {fresh.manifest_hash[:14]}\u2026"
        )

    prev_names = set(previous.modules)
    fresh_names = set(fresh.modules)
    for name in sorted(fresh_names - prev_names):
        diffs.append(f"+ {name}")
    for name in sorted(prev_names - fresh_names):
        diffs.append(f"- {name}")
    for name in sorted(prev_names & fresh_names):
        a = previous.modules[name]
        b = fresh.modules[name]
        if a.kind != b.kind:
            diffs.append(f"~ {name}: kind {a.kind} -> {b.kind}")
        if a.constraint != b.constraint:
            diffs.append(f"~ {name}: constraint {a.constraint} -> {b.constraint}")
        if (a.commit or "") != (b.commit or ""):
            ac = (a.commit or "-")[:10]
            bc = (b.commit or "-")[:10]
            diffs.append(f"~ {name}: commit {ac} -> {bc}")
        if a.content_hash != b.content_hash:
            diffs.append(f"~ {name}: content hash differs")
    return diffs


def sync_app_impl(
    app_dir: Path,
    *,
    frozen: bool = False,
    force: bool = False,
) -> None:
    """Make ``modules/`` exactly match ``nsx.lock``.

    Args:
        frozen: Error on any drift instead of correcting it (CI mode).
        force: Re-vendor every module even if its content_hash matches.
    """

    from .module_registry import (
        _update_module_clone,
        _vendor_git_module_at_commit,
        _vendor_packaged_module_into_app,
    )

    lock = read_lock(app_dir)
    if lock is None:
        if frozen:
            raise SystemExit(
                f"{app_dir / 'nsx.lock'} not found. Run `nsx lock` first (or drop --frozen)."
            )
        # No lock yet — produce one, then sync against it.
        lock_app_impl(app_dir)
        lock = read_lock(app_dir)
        assert lock is not None  # noqa: S101 — invariant guaranteed by lock_app_impl

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)

    # Detect manifest drift — the user edited nsx.yml since the lock was written.
    current_manifest_hash = hash_manifest(app_dir / "nsx.yml")
    if lock.manifest_hash and lock.manifest_hash != current_manifest_hash:
        if frozen:
            raise SystemExit(
                "nsx.yml has changed since nsx.lock was written. "
                "Run `nsx lock` to refresh, or drop --frozen."
            )
        print("warning: nsx.yml has changed since nsx.lock was written; run `nsx lock` to refresh.")

    changed = 0
    for name, entry in lock.modules.items():
        # Vendored / unresolved modules don't necessarily have a registry
        # entry; trust the path recorded in the lock for those.
        if entry.kind in ("vendored", "unresolved"):
            vendored_dir = app_dir / entry.vendored_at
        else:
            vendored_dir = _resolved_module_path(app_dir, name, registry)
        on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None

        if entry.kind == "local":
            # Source path is mirrored into modules/<name>/. If the module
            # has a configured local_path (e.g. via source: { path: <p> }),
            # mirror it into place; otherwise the user is managing the
            # directory in-tree and we just verify the hash.
            try:
                project_entry = _registry_project_entry(registry, entry.project)
            except Exception:  # noqa: BLE001 — best-effort lookup
                project_entry = None
            if project_entry is not None and project_entry.local_path:
                from .module_registry import _vendor_local_module_into_app

                _vendor_local_module_into_app(app_dir, name, registry)
                on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
            if frozen and on_disk_hash != entry.content_hash:
                raise SystemExit(
                    f"Local module '{name}' content drifted from lock "
                    f"({entry.vendored_at}). Refusing under --frozen."
                )
            continue

        if entry.kind == "vendored":
            # Committed in the app (source: { vendored: true }) — sync never
            # writes to it. Verify the on-disk content still matches what the
            # lock recorded.
            if on_disk_hash != entry.content_hash:
                msg = (
                    f"Vendored module '{name}' content drifted from lock "
                    f"({entry.vendored_at}). Run `nsx lock` to re-record, "
                    "or revert the changes."
                )
                if frozen:
                    raise SystemExit(msg)
                print(f"warning: {msg}")
            continue

        if entry.kind == "unresolved":
            # Upstream wasn't reachable when the lock was written. Verify the
            # on-disk content still matches; can't re-fetch.
            if on_disk_hash != entry.content_hash:
                msg = (
                    f"Unresolved module '{name}' content drifted from lock "
                    f"({entry.vendored_at}); upstream {entry.url} is not reachable."
                )
                if frozen:
                    raise SystemExit(msg)
                print(f"warning: {msg}")
            continue

        needs_refresh = force or (on_disk_hash != entry.content_hash)
        if not needs_refresh:
            continue

        if frozen and on_disk_hash is not None:
            raise SystemExit(
                f"Module '{name}' on-disk content does not match nsx.lock "
                f"({entry.vendored_at}). Refusing to modify under --frozen."
            )

        if entry.kind == "packaged":
            _vendor_packaged_module_into_app(app_dir, name, registry)
        elif entry.kind == "git":
            # Re-vendor at the exact locked commit (not the branch tip).
            if entry.commit:
                _vendor_git_module_at_commit(app_dir, name, registry, entry.commit)
            else:
                _update_module_clone(app_dir, name, registry)
        changed += 1

    # Always refresh the packaged cmake tree and regenerate modules.cmake +
    # modules/.gitignore — these are cheap and keep the build inputs aligned.
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)

    if changed:
        print(f"Synced {changed} module{'s' if changed != 1 else ''} from nsx.lock.")
    else:
        print("All modules already match nsx.lock.")


def outdated_app_impl(app_dir: Path, *, as_json: bool = False) -> int:
    """Report git modules whose locked commit lags behind the upstream constraint.

    Returns the number of outdated modules so callers (e.g. CI) can use
    the exit code as a signal.
    """

    lock = read_lock(app_dir)
    if lock is None:
        raise SystemExit(f"{app_dir / 'nsx.lock'} not found. Run `nsx lock` first.")

    rows: list[tuple[str, str, str, str, str]] = []  # name, constraint, locked, upstream, status
    full_rows: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []

    for name, entry in sorted(lock.modules.items()):
        if entry.kind != "git":
            continue
        if not entry.url:
            skipped.append((name, "no url"))
            continue
        try:
            upstream = resolve_commit(entry.url, entry.tag or entry.constraint)
        except ResolutionError as exc:
            skipped.append((name, str(exc)))
            continue
        locked = (entry.commit or "").lower()
        if upstream.lower() == locked:
            status = "up-to-date"
        else:
            status = "outdated"
        rows.append((name, entry.constraint, locked[:10], upstream[:10], status))
        full_rows.append(
            {
                "module": name,
                "constraint": entry.constraint,
                "locked": locked,
                "upstream": upstream.lower(),
                "status": status,
                "url": entry.url or "",
            }
        )

    outdated = [r for r in rows if r[4] == "outdated"]

    if as_json:
        import json

        payload = {
            "checked": full_rows,
            "skipped": [{"module": n, "reason": r} for n, r in skipped],
            "outdated_count": len(outdated),
        }
        print(json.dumps(payload, indent=2))
        return len(outdated)

    if not rows and not skipped:
        print("No git modules to check.")
        return 0

    name_w = max((len(r[0]) for r in rows), default=4)
    cons_w = max((len(r[1]) for r in rows), default=10)
    header = f"{'module'.ljust(name_w)}  {'constraint'.ljust(cons_w)}  {'locked'.ljust(10)}  {'upstream'.ljust(10)}  status"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r[0].ljust(name_w)}  {r[1].ljust(cons_w)}  {r[2].ljust(10)}  {r[3].ljust(10)}  {r[4]}"
        )

    if skipped:
        print()
        for name, reason in skipped:
            print(f"skipped: {name} ({reason})")

    print()
    if outdated:
        names = ", ".join(r[0] for r in outdated)
        print(f"{len(outdated)} outdated: {names}")
        print("Run `nsx update` (all) or `nsx update --module <name>` to refresh.")
    else:
        print("All git modules are up-to-date with their constraints.")
    return len(outdated)


def update_app_impl(
    app_dir: Path,
    *,
    modules: list[str] | None = None,
) -> None:
    """Re-resolve constraints to current upstream and re-vendor.

    Equivalent to ``nsx lock --update [--module ...]`` followed by
    ``nsx sync``.
    """

    lock_app_impl(app_dir, update=True, modules=modules)
    sync_app_impl(app_dir)
