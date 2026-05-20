"""Module add / remove / update / register operations."""

from __future__ import annotations

import copy
from pathlib import Path

from .._errors import NSXConfigError, NSXModuleError, NSXResolutionError
from ..constants import DEFAULT_TOOLCHAIN
from ..metadata import registry_entry_for_module, validate_nsx_module_metadata
from ..models import ModuleChange, ModuleEntry, ProjectEntry
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


def _safe_registry_revision(name: str, registry: dict) -> str | None:
    """Best-effort registry revision lookup for ``ModuleChange`` records.

    Returns ``None`` for modules absent from the registry (local,
    vendored, app-only overrides) so callers don't have to guard each
    call site.
    """

    try:
        return registry_entry_for_module(registry, name).revision
    except Exception:
        return None


def add_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    local: bool = False,
    vendored: bool = False,
    dry_run: bool = False,
) -> list[ModuleChange]:
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
        if dry_run:
            return [
                ModuleChange(
                    name=module_name, before=None, after=None, action="added", dry_run=True
                )
            ]
        target_dir = app_dir / "modules" / module_name
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
        return [ModuleChange(name=module_name, before=None, after=None, action="added")]

    if local:
        # Local modules bypass registry resolution entirely.
        existing = _module_names_from_nsx(nsx_cfg)
        if module_name in existing:
            raise NSXModuleError(f"Module '{module_name}' is already enabled in nsx.yml")
        if dry_run:
            return [
                ModuleChange(
                    name=module_name, before=None, after=None, action="added", dry_run=True
                )
            ]
        modules_list = nsx_cfg.setdefault("modules", [])
        modules_list.append({"name": module_name, "local": True})
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        return [ModuleChange(name=module_name, before=None, after=None, action="added")]

    registry = _effective_registry(_load_registry(), nsx_cfg)

    enabled = _module_names_from_nsx(nsx_cfg)
    desired_modules = _unique_preserving_order(enabled + [module_name])
    new_modules = _resolve_module_closure(
        desired_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
        acquire_missing=not dry_run,
    )
    enabled_set = set(enabled)
    added = [n for n in new_modules if n not in enabled_set]
    if dry_run:
        return [
            ModuleChange(
                name=name,
                before=None,
                after=_safe_registry_revision(name, registry),
                action="added",
                dry_run=True,
            )
            for name in added
        ]

    local_names = _local_module_names(nsx_cfg)
    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _acquire_modules_for_app(app_dir, new_modules, registry, local_modules=local_names)
    _write_modules_gitignore(app_dir, nsx_cfg)

    return [
        ModuleChange(
            name=name,
            before=None,
            after=_safe_registry_revision(name, registry),
            action="added",
        )
        for name in added
    ]


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
) -> list[ModuleChange]:
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
            return [
                ModuleChange(
                    name=module_name, before=None, after=None, action="removed", dry_run=True
                )
            ]
        nsx_cfg["modules"] = [
            m
            for m in nsx_cfg.get("modules", [])
            if not (isinstance(m, dict) and m.get("name") == module_name)
        ]
        _save_app_cfg(app_dir, nsx_cfg)
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)
        return [ModuleChange(name=module_name, before=None, after=None, action="removed")]

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
    removed_sorted = sorted(remove_set)
    if dry_run:
        return [
            ModuleChange(
                name=name,
                before=_safe_registry_revision(name, registry),
                after=None,
                action="removed",
                dry_run=True,
            )
            for name in removed_sorted
        ]

    _update_nsx_cfg_modules(nsx_cfg, new_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)
    for removed_name in removed_sorted:
        _remove_vendored_module_from_app(app_dir, removed_name, registry)

    return [
        ModuleChange(
            name=name,
            before=_safe_registry_revision(name, registry),
            after=None,
            action="removed",
        )
        for name in removed_sorted
    ]


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
) -> list[ModuleChange]:
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

    # Capture the recorded revision of each module before resolving the
    # new closure so ``ModuleChange.before`` reflects the on-disk state.
    before_revisions: dict[str, str | None] = {}
    for entry in nsx_cfg.get("modules", []) or []:
        if isinstance(entry, dict) and entry.get("name") in to_update:
            rev = entry.get("revision")
            before_revisions[entry["name"]] = rev if isinstance(rev, str) else None

    resolved_modules = _resolve_module_closure(
        current_modules,
        app_dir=app_dir,
        nsx_cfg=nsx_cfg,
        registry=registry,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )

    def _change(name: str, *, dry: bool) -> ModuleChange:
        before = before_revisions.get(name)
        after = _safe_registry_revision(name, registry)
        action = "updated" if before != after else "noop"
        return ModuleChange(name=name, before=before, after=after, action=action, dry_run=dry)

    if dry_run:
        return [_change(name, dry=True) for name in sorted(to_update)]

    _update_nsx_cfg_modules(nsx_cfg, resolved_modules, registry)
    _save_app_cfg(app_dir, nsx_cfg)
    _write_app_module_file(app_dir, nsx_cfg)
    for name in resolved_modules:
        if name in to_update:
            _update_module_clone(app_dir, name, registry)

    return [_change(name, dry=False) for name in sorted(to_update)]


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
) -> ModuleChange:
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

    after_revision = project_entry.revision or "main"
    if dry_run:
        return ModuleChange(
            name=module_name,
            before=None,
            after=after_revision,
            action="added",
            dry_run=True,
        )

    _save_app_cfg(app_dir, target_cfg)
    _write_app_module_file(app_dir, target_cfg)
    effective = _effective_registry(base_registry, target_cfg)
    _acquire_modules_for_app(app_dir, [module_name], effective)
    _write_modules_gitignore(app_dir, target_cfg)

    return ModuleChange(
        name=module_name,
        before=None,
        after=after_revision,
        action="added",
    )
