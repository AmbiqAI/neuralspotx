"""Project selection and materialization checks for targeted lock updates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError
from ..metadata import registry_entry_for_module
from ..module_registry import _is_packaged_module
from ..nsx_lock import LockKind, NsxLock, ResolvedModule
from ..project_config import _registry_project_entry


@dataclass
class LockInputs:
    """One target's effective configuration and acquired dependency closure."""

    config: dict[str, Any]
    registry: dict[str, Any]
    module_names: list[str]
    local_names: set[str]
    vendored_names: set[str]


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


def validate_materialization(app_dir: Path, lock: NsxLock) -> None:
    """Reject incompatible Git outcomes that cannot share one source tree."""
    groups: dict[Path, list[tuple[str, ResolvedModule]]] = {}
    for name, entry in lock.modules.items():
        if entry.kind in (LockKind.GIT, LockKind.UNRESOLVED):
            groups.setdefault((app_dir / entry.vendored_at).resolve(), []).append((name, entry))
    for rows in groups.values():
        if len(rows) < 2:
            continue
        identities = {(row.kind, row.url, row.commit, row.content_hash) for _, row in rows}
        if len(identities) > 1:
            names = ", ".join(sorted(name for name, _ in rows))
            raise NSXConfigError(
                f"Targeted update for board '{lock.target.get('board', '<unspecified>')}' "
                f"cannot materialize modules [{names}] in one shared project directory: "
                "their resolved artifacts differ or include mixed Git/unresolved entries. "
                "Align project/module revisions, retry unreachable refs, or use separate "
                "project paths. The affected lock section was not written."
            )
