"""Module add / remove / update / register operations."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError, NSXModuleError, NSXResolutionError
from ..metadata import registry_entry_for_module, validate_nsx_module_metadata
from ..models import AppConfig, ModuleChange, ModuleEntry, ProjectEntry
from ..module_registry import (
    _acquire_modules_for_app,
    _remove_vendored_module_from_app,
)
from ..nsx_lock import read_lock, read_lock_file
from ..project_config import (
    _board_key_for_app,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _metadata_storage_path,
    _read_yaml,
    _registry_project_entry,
    _save_app_cfg,
    _write_app_module_file,
    _write_modules_gitignore,
)
from ._common import _scaffold_vendored_module
from ._lock import lock_app_impl


def _app_has_lock(app_dir: Path) -> bool:
    """True when the app already has a lock file on disk.

    Every app commits a single combined ``nsx.lock`` (with a ``targets:``
    map). ``add`` / ``remove`` only refresh the lock when one already
    exists so a manifest edit on an unlocked app stays offline until the
    user runs ``nsx lock``.
    """

    return (app_dir / "nsx.lock").exists() or any(app_dir.glob("nsx.*.lock"))


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
    path: str | None = None,
    boards: tuple[str, ...] = (),
    dry_run: bool = False,
) -> list[ModuleChange]:
    """Add a direct dependency to an app's ``modules:`` list.

    The ``modules:`` list holds only an app's *direct* dependencies; the full
    closure is recomputed from the board profile + these direct deps at lock
    time. This appends a single entry and (when the app is already locked)
    refreshes the lock so the new dependency is resolved and materialized.

    Source kinds (mutually exclusive):
        local: ``local: true`` -- a bare in-tree module under
            ``modules/<name>/`` that is gitignored and bypasses the registry.
        vendored: ``source: { vendored: true }`` -- committed in-tree under
            ``modules/<name>/`` and never touched by ``nsx sync``. A minimal
            ``nsx-module.yaml`` / ``CMakeLists.txt`` is scaffolded if absent.
        path: ``source: { path: <p> }`` -- an external linked checkout.
        (none): resolved from the module registry.

    boards: optional per-entry filter scoping the dependency to those boards
        (a subset of the app's supported targets); empty means all targets.
    """

    selected = [
        flag
        for flag, on in (("--local", local), ("--vendored", vendored), ("--path", bool(path)))
        if on
    ]
    if len(selected) > 1:
        raise NSXConfigError(f"{' and '.join(selected)} are mutually exclusive")

    nsx_cfg = _load_app_cfg(app_dir)
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    declared = {module.name for module in app_cfg.modules}
    if module_name in declared:
        raise NSXModuleError(
            f"Module '{module_name}' is already a direct dependency in nsx.yml"
        )

    if boards:
        supported = set(app_cfg.targets())
        unknown = sorted(b for b in boards if b not in supported)
        if supported and unknown:
            listed = ", ".join(sorted(supported))
            raise NSXConfigError(
                f"--board {', '.join(unknown)} not in the app's supported targets "
                f"({listed})"
            )

    entry: dict[str, Any] = {"name": module_name}
    if local:
        entry["local"] = True
    elif vendored:
        entry["source"] = {"vendored": True}
    elif path:
        entry["source"] = {"path": path}
    if boards:
        entry["boards"] = list(boards)

    if dry_run:
        return [
            ModuleChange(name=module_name, before=None, after=None, action="added", dry_run=True)
        ]

    if vendored:
        target_dir = app_dir / "modules" / module_name
        target_dir.mkdir(parents=True, exist_ok=True)
        _scaffold_vendored_module(target_dir, module_name)

    manifest_path = app_dir / "nsx.yml"
    original_text = manifest_path.read_text(encoding="utf-8")
    nsx_cfg.setdefault("modules", []).append(entry)
    _save_app_cfg(app_dir, nsx_cfg)

    # Refresh the lock(s) so the new direct dep is resolved into the closure,
    # materialized, and reflected in the CMake glue. Only do this when the app
    # is already locked, so editing an unlocked manifest stays offline; the
    # user runs ``nsx lock`` to materialize. On any resolution failure (e.g. a
    # mistyped registry module), roll the manifest back so the add is atomic.
    if _app_has_lock(app_dir):
        try:
            lock_app_impl(app_dir, quiet=True)
        except Exception:
            manifest_path.write_text(original_text, encoding="utf-8")
            raise
    else:
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)

    registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app_dir)
    return [
        ModuleChange(
            name=module_name,
            before=None,
            after=_safe_registry_revision(module_name, registry),
            action="added",
        )
    ]


def remove_module_impl(
    app_dir: Path,
    module_name: str,
    *,
    dry_run: bool = False,
) -> list[ModuleChange]:
    """Remove a direct dependency from an app's ``modules:`` list.

    Only *direct* dependencies can be removed. The closure is recomputed at
    lock time, so dropping a direct dep also drops any transitive modules it
    alone pulled in. Board-baseline modules (provided by the board profile,
    not listed in ``modules:``) cannot be removed individually.
    """

    nsx_cfg = _load_app_cfg(app_dir)
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    declared = {module.name: module for module in app_cfg.modules}
    if module_name not in declared:
        raise NSXModuleError(
            f"Module '{module_name}' is not a direct dependency in nsx.yml. "
            "Modules provided by the board baseline cannot be removed individually."
        )

    module = declared[module_name]
    is_in_tree = module.is_local or module.is_vendored

    if dry_run:
        return [
            ModuleChange(name=module_name, before=None, after=None, action="removed", dry_run=True)
        ]

    manifest_path = app_dir / "nsx.yml"
    original_text = manifest_path.read_text(encoding="utf-8")
    nsx_cfg["modules"] = [
        m
        for m in nsx_cfg.get("modules", [])
        if not (
            (isinstance(m, dict) and m.get("name") == module_name)
            or (isinstance(m, str) and m == module_name)
        )
    ]
    _save_app_cfg(app_dir, nsx_cfg)

    if _app_has_lock(app_dir):
        try:
            lock_app_impl(app_dir, quiet=True)
        except Exception:
            manifest_path.write_text(original_text, encoding="utf-8")
            raise
    else:
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)

    # In-tree directories are removed only after the manifest (and any lock) no
    # longer references the module, so a failed relock leaves the files intact
    # for the rolled-back manifest. A ``--local`` / ``--vendored`` entry owns its
    # ``modules/<name>/`` directory outright; a registry-resolved module (including
    # one backed by a local-path project) is cleaned up via the registry helper.
    #
    # Dropping the direct dep does not guarantee the module left the closure: it
    # may still be pulled by the board baseline or transitively by another direct
    # dependency, in which case the relocked ``nsx.lock`` still records it. Deleting
    # its directory then would leave ``modules/`` inconsistent with the lock, so we
    # skip cleanup while any target section still requires the module.
    still_required = False
    lock_file = read_lock_file(app_dir)
    if lock_file is not None:
        still_required = any(
            module_name in section.modules for section in lock_file.targets.values()
        )

    if not still_required:
        if is_in_tree:
            in_tree_dir = app_dir / "modules" / module_name
            if in_tree_dir.is_dir():
                shutil.rmtree(in_tree_dir)
        else:
            registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app_dir)
            _remove_vendored_module_from_app(app_dir, module_name, registry)

    return [ModuleChange(name=module_name, before=None, after=None, action="removed")]


def update_modules_impl(
    app_dir: Path,
    *,
    module_name: str | None = None,
    dry_run: bool = False,
) -> list[ModuleChange]:
    """Re-resolve the app's lock to current upstream revisions.

    In schema v2 the ``modules:`` list records only direct deps and does not
    pin registry revisions (the lock does), so ``update`` re-resolves and
    rewrites the lock rather than editing ``nsx.yml``. With a module name it
    updates just that module's lock entry; otherwise it updates every module.
    """

    board_key = _board_key_for_app(app_dir)
    before_lock = read_lock(app_dir, board_key)
    before = (
        {name: entry.commit for name, entry in before_lock.modules.items()}
        if before_lock is not None
        else {}
    )

    if module_name:
        # A module may be scoped to a non-default board via ``modules[].boards``,
        # so validate the name against every target section's closure rather than
        # just the default board's lock; otherwise valid board-specific updates
        # would be rejected before ``lock_app_impl`` can refresh all targets.
        lock_file = read_lock_file(app_dir)
        if lock_file is not None:
            known = {
                name for section in lock_file.targets.values() for name in section.modules
            }
            if module_name not in known:
                raise NSXModuleError(
                    f"Module '{module_name}' is not in the app's resolved closure (nsx.lock)"
                )

    if dry_run:
        names = [module_name] if module_name else sorted(before)
        return [
            ModuleChange(
                name=name, before=before.get(name), after=before.get(name), action="noop", dry_run=True
            )
            for name in names
        ]

    after_lock = lock_app_impl(
        app_dir,
        update=True,
        modules=[module_name] if module_name else None,
        quiet=True,
    )
    after = {name: entry.commit for name, entry in after_lock.modules.items()}

    names = [module_name] if module_name else sorted(set(before) | set(after))
    changes: list[ModuleChange] = []
    for name in names:
        before_rev = before.get(name)
        after_rev = after.get(name)
        action = "updated" if before_rev != after_rev else "noop"
        changes.append(ModuleChange(name=name, before=before_rev, after=after_rev, action=action))
    return changes


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
    registry = _effective_registry(base_registry, nsx_cfg, app_dir=app_dir)

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
    effective = _effective_registry(base_registry, target_cfg, app_dir=app_dir)
    _acquire_modules_for_app(app_dir, [module_name], effective)
    _write_modules_gitignore(app_dir, target_cfg)

    return ModuleChange(
        name=module_name,
        before=None,
        after=after_revision,
        action="added",
    )
