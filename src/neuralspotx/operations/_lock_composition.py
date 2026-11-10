"""Bind writable lock composition to the exact resolved Git artifacts."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any

from .. import module_cache
from .._errors import NSXLockError
from ..board_plan import resolve_board_plan
from ..constants import DEFAULT_TOOLCHAIN
from ..module_registry import _module_names_from_nsx, _resolve_module_closure
from ..module_registry._composition import board_composition
from ..module_registry._metadata import metadata_cache_scope
from ..module_registry._vendoring import _strip_git_metadata
from ..nsx_lock import LockKind, NsxLock, hash_tree
from ..nsx_lock._composition import BoardComposition
from ..project_config import _module_clone_dir
from ..subprocess_utils import git_clone_at_commit


def resolved_board_composition(
    app_dir: Path, config: dict[str, Any], registry: dict[str, Any], lock: NsxLock
) -> BoardComposition | None:
    plan = resolve_board_plan(app_dir, config)
    if plan is None or plan.descriptor.bsp.module not in lock.modules:
        return None
    snapshot_registry = copy.deepcopy(registry)
    projects: dict[str, tuple[str, str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="nsx-bsp-lock-") as temporary:
        for module in lock.modules.values():
            if module.kind != LockKind.GIT:
                continue
            if not module.url or not module.commit:
                raise NSXLockError("A Git BSP composition input requires a resolved URL and commit")
            identity = (module.url, module.commit, module.content_hash)
            if module.project in projects:
                if projects[module.project] != identity:
                    raise NSXLockError(
                        f"Conflicting locked revisions for project '{module.project}'"
                    )
                continue
            projects[module.project] = identity
            existing = _module_clone_dir(app_dir, module.project, registry)
            if existing.is_dir() and hash_tree(existing) == module.content_hash:
                source = existing
            else:
                source = Path(temporary) / str(len(projects))
                if not module_cache.lookup(module.content_hash, source):
                    git_clone_at_commit(module.url, source, module.commit)
                    _strip_git_metadata(source)
                    if hash_tree(source) != module.content_hash:
                        raise NSXLockError(
                            f"Locked artifact integrity mismatch for '{module.project}'"
                        )
            snapshot_registry["projects"][module.project]["local_path"] = str(source)

        # Initial graph discovery may have read an older vendored checkout.
        # Never publish new metadata fingerprints beside that older graph.
        with metadata_cache_scope(fresh=True):
            resolved = _resolve_module_closure(
                _module_names_from_nsx(config),
                app_dir=app_dir,
                nsx_cfg=config,
                registry=snapshot_registry,
                default_toolchain=DEFAULT_TOOLCHAIN,
            )
            if resolved != list(lock.modules):
                raise NSXLockError(
                    "Dependency graph changed in the resolved Git artifacts; no lock was written. "
                    "Refresh the app-local module sources to the selected revisions and rerun `nsx lock`."
                )
            return board_composition(app_dir, config, snapshot_registry, resolved)
