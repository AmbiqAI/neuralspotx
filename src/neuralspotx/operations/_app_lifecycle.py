"""App lifecycle: ``create_app_impl`` and ``init_module_impl``."""

from __future__ import annotations

import importlib.resources as resources
import json
import shutil
from pathlib import Path

from .._errors import NSXConfigError, NSXModuleError
from .._io import info, warn
from ..constants import (
    DEFAULT_SOC_FOR_BOARD,
    DEFAULT_TOOLCHAIN,
    normalize_board,
    normalize_soc,
)
from ..metadata import load_yaml, validate_nsx_module_metadata
from ..models import ModuleChange
from ..module_registry import (
    _acquire_modules_for_app,
    _generate_nsx_config,
    _module_names_from_nsx,
    _resolve_module_closure,
    _update_nsx_cfg_modules,
)
from ..project_config import (
    _copy_packaged_tree,
    _effective_registry,
    _load_registry,
    _nsx_tool_major,
    _nsx_tool_version,
    _save_app_cfg,
    _unique_preserving_order,
    _write_app_module_file,
    _write_modules_gitignore,
)
from ..templating import render_template_tree
from ._common import (
    ProfileStatus,
    _log,
    _module_package_name,
    _module_target_name,
)


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

    # Silently normalize case at the input boundary so users can pass
    # ``APOLLO510`` / ``apollo330MP_EVB`` etc. without surprise failures.
    board = normalize_board(board)
    soc = normalize_soc(soc) or DEFAULT_SOC_FOR_BOARD.get(board)
    if soc is None:
        raise NSXConfigError(f"Unable to infer --soc for board '{board}'. Pass --soc explicitly.")

    template_root = resources.files("neuralspotx.templates").joinpath("external_app")
    with resources.as_file(template_root) as src_template:
        if not src_template.exists():
            raise NSXConfigError(f"Template directory not found: {src_template}")

        if app_dir.exists() and any(app_dir.iterdir()) and not force:
            raise NSXConfigError(f"App directory already exists and is not empty: {app_dir}")

        created_fresh = not app_dir.exists()
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

    try:
        return _create_app_body(
            app_dir,
            app_name=app_name,
            board=board,
            soc=soc,
            base_registry=base_registry,
            no_bootstrap=no_bootstrap,
        )
    except Exception:
        if created_fresh:
            shutil.rmtree(app_dir, ignore_errors=True)
            _log.debug("create_app: rolled back %s after failure", app_dir)
        else:
            _log.warning(
                "create_app failed; %s was pre-existing and has not been removed",
                app_dir,
            )
        raise


def _create_app_body(
    app_dir: Path,
    *,
    app_name: str,
    board: str,
    soc: str,
    base_registry: dict,
    no_bootstrap: bool,
) -> Path:
    """Inner body of create_app_impl, separated for rollback wrapping."""

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
        info(f"Created app '{app_name}' at: {app_dir}")
        info("Starter modules were not bootstrapped (--no-bootstrap).")
        info("Next steps:")
        info(f"  1) cd {app_dir}")
        info("  2) Run `nsx module list --app-dir .`")
        info("  3) Add modules with `nsx module add <module> --app-dir .`")
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
    if nsx_cfg.get("profile_status") == ProfileStatus.SCAFFOLD:
        warn(
            f"NOTE: profile '{nsx_cfg.get('profile')}' is scaffold-only. "
            "Build bring-up may not be complete yet."
        )

    info(f"Created app '{app_name}' at: {app_dir}")
    info("Next steps:")
    info(f"  1) cd {app_dir}")
    info("  2) Run `nsx configure --app-dir .`")
    info("  3) Run `nsx build --app-dir .`, `nsx flash --app-dir .`, or `nsx view --app-dir .`")
    return app_dir


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
) -> ModuleChange:
    """Create a standard custom-module skeleton."""

    module_name = (module_name or module_dir.name).strip()
    if not module_name:
        raise NSXModuleError("Module name must not be empty.")

    if module_dir.exists() and not module_dir.is_dir():
        raise NSXModuleError(f"Module path already exists and is not a directory: {module_dir}")
    if module_dir.exists() and any(module_dir.iterdir()) and not force:
        raise NSXModuleError(f"Module directory already exists and is not empty: {module_dir}")

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
            raise NSXConfigError(f"Template directory not found: {src_template}")

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

    return ModuleChange(
        name=module_name,
        before=None,
        after=version,
        action="added",
    )
