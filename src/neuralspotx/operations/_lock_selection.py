"""Project selection and materialization checks for targeted lock updates."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError
from ..metadata import registry_entry_for_module
from ..module_registry import _is_packaged_module
from ..nsx_lock import LockKind, NsxLock, ResolvedModule
from ..project_config import RegistryAuthorship, _registry_project_entry


@dataclass
class LockInputs:
    """One target's effective configuration and acquired dependency closure."""

    config: dict[str, Any]
    registry: dict[str, Any]
    module_names: list[str]
    local_names: set[str]
    vendored_names: set[str]
    used_locked_closure: bool = False
    authorship: RegistryAuthorship = field(default_factory=RegistryAuthorship)
    isolated_manifests: dict[str, str] = field(default_factory=dict)


def selected_git_modules(inputs: LockInputs, selected: frozenset[str]) -> frozenset[str]:
    """Expand selected Git modules to their materialized registry projects."""
    projects: dict[str, str] = {}
    for name in inputs.module_names:
        if name in inputs.local_names or name in inputs.vendored_names:
            continue
        if _is_packaged_module(inputs.registry, name):
            continue
        entry = registry_entry_for_module(inputs.registry, name)
        project = _registry_project_entry(inputs.registry, entry.project)
        if project.url and not project.local_path:
            projects[name] = entry.project
    selected_projects = {project for name, project in projects.items() if name in selected}
    return frozenset(name for name, project in projects.items() if project in selected_projects)


def qualified_pin_conflicts(
    previous: NsxLock, fresh: NsxLock, inputs: LockInputs, selected: frozenset[str]
) -> list[str]:
    """Explain changes to prior Git artifacts that require an explicit project update."""
    conflicts = []
    authored = inputs.authorship
    for name, row in fresh.modules.items():
        old = previous.modules.get(name)
        if old is None or old.kind != LockKind.GIT or name in selected:
            continue
        if row.kind not in (LockKind.GIT, LockKind.UNRESOLVED, LockKind.PACKAGED):
            continue
        reason = ""
        same_source = (row.project, row.url) == (old.project, old.url)
        if old.project != row.project:
            if name not in authored.module_projects:
                reason = f"registry project changed from '{old.project}'"
        elif old.url != row.url and row.project not in authored.project_urls:
            reason = "registry source URL changed"
        if same_source and old.commit == row.commit and old.content_hash != row.content_hash:
            reason = "content hash changed for the same commit"
        elif (
            old.project == row.project
            and old.constraint != row.constraint
            and name not in authored.module_revisions
            and old.commit != row.commit
        ):
            reason = "registry revision no longer identifies the qualified commit"
        if reason:
            conflicts.append(
                f"board '{fresh.target['board']}', project '{row.project}', module '{name}' "
                f"({reason}; locked {old.constraint} at {old.commit}, effective revision {row.constraint}). "
                f"To adopt it, run `nsx lock --module {name}`."
            )
    return conflicts


def validate_materialization(app_dir: Path, lock: NsxLock) -> None:
    """Reject incompatible Git outcomes that cannot share one source tree."""
    groups: dict[Path, list[tuple[str, ResolvedModule]]] = {}
    for name, entry in lock.modules.items():
        if entry.kind in (LockKind.GIT, LockKind.UNRESOLVED):
            groups.setdefault((app_dir / entry.vendored_at).resolve(), []).append((name, entry))
    for rows in groups.values():
        if len(rows) < 2:
            continue
        if all(row.kind == LockKind.UNRESOLVED for _, row in rows):
            # Unresolved rows verify local content; no remote identity is
            # materialized. Different URLs can describe the same fallback tree.
            consistent = len({row.content_hash for _, row in rows}) == 1
        else:
            identities = {(row.kind, row.url, row.commit, row.content_hash) for _, row in rows}
            consistent = len(identities) == 1
        if not consistent:
            names = ", ".join(sorted(name for name, _ in rows))
            raise NSXConfigError(
                f"Lock for board '{lock.target.get('board', '<unspecified>')}' "
                f"cannot materialize modules [{names}] in one shared project directory: "
                "their resolved artifacts differ or include mixed Git/unresolved entries. "
                "Align project/module revisions, retry unreachable refs, or use separate "
                "project paths. The affected lock section was not written."
            )
