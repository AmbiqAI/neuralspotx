"""Operator diagnostics derived from resolved locks without remote lookups."""

from __future__ import annotations

from .._logging import get_logger
from ..nsx_lock import LockKind, NsxLock
from ..nsx_lock._resolution import _looks_like_full_sha

_log = get_logger(__name__)


def warn_unpinned_git_constraints(lock: NsxLock) -> None:
    """Report Git constraints that lack a full SHA or matching recorded tag.

    Source kind, not project name, excludes packaged and local dependencies.
    Unresolved rows have no exact commit and retain their existing diagnostics.
    URLs participate in grouping but are never rendered (they may contain secrets).
    """
    groups: dict[tuple[str, str, str], list[str]] = {}
    for name, module in lock.modules.items():
        if module.kind != LockKind.GIT:
            continue
        if _looks_like_full_sha(module.constraint) or module.tag == module.constraint:
            continue
        key = (module.project, module.url or "", module.constraint)
        groups.setdefault(key, []).append(name)

    board = lock.target.get("board", "<unspecified>")
    for (project, _url, revision), names in sorted(groups.items()):
        _log.warning(
            "Unpinned Git constraint for board %r: project %r, revision %r, modules [%s]. "
            "These entries record exact commits, but re-resolution may change them. "
            "For stable re-resolution, set a tag or full 40-character commit SHA in "
            "nsx.yml module_registry.projects.%s.revision "
            "(or module_registry.modules.<module>.revision for a module override).",
            board,
            project,
            revision,
            ", ".join(sorted(names)),
            project,
        )
