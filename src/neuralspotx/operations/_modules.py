"""Module add / remove / update / register operations."""

from __future__ import annotations

import copy
from pathlib import Path

from .._errors import NSXConfigError, NSXModuleError, NSXResolutionError
from ..constants import DEFAULT_TOOLCHAIN
from ..metadata import validate_nsx_module_metadata
from ..models import ModuleEntry, ProjectEntry
from ..module_registry import (
    _acquire_modules_for_app,
    _load_module_metadata,
    _local_module_names,
    _module_dependents,
    _module_names_from_nsx,
    _remove_vendored_module_from_app,
    _resolve_module_closure,
    _update_module_clone,
    _update_nsx_cfg_modules,
)
from ..project_config import (
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _metadata_storage_path,
    _read_yaml,
    _registry_project_entry,
    _save_app_cfg,
    _unique_preserving_order,
    _write_app_module_file,
    _write_modules_gitignore,
)
from ._common import _scaffold_vendored_module
from ._lock import lock_app_impl


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
        raise NSXConfigError("--local and --vendored are mutually exclusive")

    nsx_cfg = _load_app_cfg(app_dir)

    if vendored:
        existing = _module_names_from_nsx(nsx_cfg)
        if module_name in existing:
            raise NSXModuleError(f"Module '{module_name}' is already enabled in nsx.yml")
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
            raise NSXModuleError(f"Module '{module_name}' is already enabled in nsx.yml")
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
        raise NSXModuleError(f"Module '{module_name}' is not enabled in nsx.yml")

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
        raise NSXModuleError(
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
            raise NSXModuleError(f"Module '{module_name}' is not enabled in nsx.yml")
        if module_name in local_names:
            raise NSXModuleError(
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
        raise NSXConfigError(f"Metadata file does not exist: {metadata_path}")

    module_data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(module_data, str(metadata_path))
    declared_name = module_data.get("module", {}).get("name")
    if declared_name != module_name:
        raise NSXConfigError(
            f"Metadata module name mismatch: expected '{module_name}', found '{declared_name}'"
        )

    project_name = project
    project_entry: ProjectEntry
    if project_local_path and (project_url or project_revision or project_path):
        raise NSXConfigError(
            "Use either --project-local-path OR (--project-url --project-revision --project-path), not both."
        )
    if project_local_path:
        local_path = project_local_path.resolve()
        if not local_path.exists():
            raise NSXConfigError(f"--project-local-path does not exist: {local_path}")
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
            raise NSXResolutionError(
                f"Project '{project_name}' is not in registry. "
                "Provide --project-local-path OR --project-url."
            )

    current_modules = registry.get("modules", {})
    if module_name in current_modules and not override:
        raise NSXModuleError(
            f"Module '{module_name}' already exists in effective registry. "
            "Use --override to replace it for this app."
        )

    target_cfg = copy.deepcopy(nsx_cfg)
    module_registry = target_cfg.setdefault("module_registry", {})
    if not isinstance(module_registry, dict):
        raise NSXConfigError("nsx.yml: module_registry must be a mapping")
    projects = module_registry.setdefault("projects", {})
    modules = module_registry.setdefault("modules", {})
    if not isinstance(projects, dict) or not isinstance(modules, dict):
        raise NSXConfigError("nsx.yml: module_registry.projects/modules must be mappings")

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
