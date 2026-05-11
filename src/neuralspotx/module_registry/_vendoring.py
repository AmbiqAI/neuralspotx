"""Vendoring and cloning helpers for git/local/packaged modules into apps."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .. import module_cache
from .._errors import NSXConfigError
from ..metadata import registry_entry_for_module
from ..project_config import (
    _is_packaged_module,
    _module_clone_dir,
    _registry_project_entry,
    _vendored_target_dir,
)
from ..subprocess_utils import git_clone, git_clone_at_commit
from ..tooling import require_tool as _require_tool
from ._metadata import packaged_module_source_dir
from ._rmtree import _rmtree


def _ensure_module_cloned(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Ensure a git-hosted module's project is present in the app.

    The module is cloned from its registry URL, then the ``.git``
    directory is removed so the result is a plain copy — not a nested
    git repository.  This keeps the ``modules/`` directory safely
    gitignored: ``nsx configure`` will re-clone any missing modules.
    """

    if _is_packaged_module(registry, module_name):
        return  # packaged modules are copied, not cloned

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)

    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return  # user-registered local module, vendor instead of clone

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)
    if clone_dir.exists():
        return  # already present

    url = project_entry.url
    if not url:
        raise NSXConfigError(
            f"Module '{module_name}' project '{entry.project}' has no URL in registry. "
            "Cannot clone."
        )

    _require_tool("git")
    git_clone(url, clone_dir, revision=entry.revision)

    # Remove .git so the module is a plain copy, not a nested repo.
    git_dir = clone_dir / ".git"
    if git_dir.exists():
        _rmtree(git_dir)


def _update_module_clone(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Re-acquire a module at the registry revision.

    Since cloned modules have their ``.git`` directory removed (they are
    plain copies), an update deletes the existing copy and re-clones at
    the desired revision.
    """

    if _is_packaged_module(registry, module_name):
        return

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)
    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)
    if clone_dir.exists():
        _rmtree(clone_dir)
    _ensure_module_cloned(app_dir, module_name, registry)


def _vendor_git_module_at_commit(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
    commit: str,
    *,
    content_hash: str | None = None,
) -> None:
    """Re-vendor a git module at an exact commit SHA.

    Used by ``nsx sync`` to faithfully restore an ``nsx.lock`` entry,
    independent of where the module's branch currently points. A full
    clone is performed (shallow clones may not contain the commit), the
    requested commit is checked out detached, and ``.git`` is stripped.

    When ``content_hash`` is provided, the on-disk module-artifact cache
    (see :mod:`neuralspotx.module_cache`) is consulted first: a cache
    hit avoids the network round-trip entirely. On a cache miss the
    clone proceeds as before and the resulting tree is written back to
    the cache for future runs. The cache is best-effort and any
    failure transparently falls back to a fresh clone.
    """

    if _is_packaged_module(registry, module_name):
        return

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)

    # User-registered local modules: copy from local_path; ignore commit.
    if project_entry.local_path:
        _vendor_local_module_into_app(app_dir, module_name, registry)
        return

    url = project_entry.url
    if not url:
        raise NSXConfigError(
            f"Module '{module_name}' project '{entry.project}' has no URL in registry; cannot sync."
        )

    clone_dir = _module_clone_dir(app_dir, entry.project, registry)

    # Fast path: try to materialise from the content-addressed cache.
    if content_hash and module_cache.lookup(content_hash, clone_dir):
        return

    if clone_dir.exists():
        _rmtree(clone_dir)

    _require_tool("git")
    git_clone_at_commit(url, clone_dir, commit)

    git_dir = clone_dir / ".git"
    if git_dir.exists():
        _rmtree(git_dir)

    # Slow path completed: seed the cache so the next caller can skip
    # the clone. ``populate`` is best-effort; failures are silent.
    if content_hash:
        module_cache.populate(content_hash, clone_dir)


def _vendor_local_module_into_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Copy a user-registered local module into the app's modules/ directory."""

    entry = registry_entry_for_module(registry, module_name)
    project_entry = _registry_project_entry(registry, entry.project)
    if not project_entry.local_path:
        return

    source_dir = Path(project_entry.local_path).expanduser().resolve()
    destination_dir = _module_clone_dir(app_dir, entry.project, registry)

    if destination_dir.resolve() == source_dir.resolve():
        return
    if destination_dir.resolve().is_relative_to(source_dir.resolve()):
        return
    if source_dir.resolve().is_relative_to(destination_dir.resolve()):
        return

    if destination_dir.exists():
        _rmtree(destination_dir)
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        destination_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
    )


def _vendor_packaged_module_into_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    """Copy a packaged module (board/cmake) from the neuralspotx package into the app.

    Always sources from the packaged wheel resource (never the
    app-local materialized copy). If we resolved the source via
    ``_module_metadata_path(..., app_dir=app_dir)`` and the user had
    mutated ``modules/<name>/``, the resolver would prefer that
    vendored copy and the subsequent copy would be a same-path no-op,
    leaving the on-disk tree drifted from the lock indefinitely.
    """

    if not _is_packaged_module(registry, module_name):
        return  # git-hosted modules are cloned, not copied

    entry = registry_entry_for_module(registry, module_name)
    # Use the public helper which always passes ``app_dir=None`` and
    # so always returns the wheel resource path.
    source_dir = packaged_module_source_dir(module_name, entry, registry)
    destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)

    if destination_dir.resolve() == source_dir.resolve():
        return
    if destination_dir.resolve().is_relative_to(source_dir.resolve()):
        return

    preserve_existing = destination_dir == app_dir / "cmake" / "nsx"
    if destination_dir.exists() and not preserve_existing:
        _rmtree(destination_dir)
    destination_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_dir,
        destination_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
    )


def _remove_vendored_module_from_app(
    app_dir: Path,
    module_name: str,
    registry: dict[str, Any],
) -> None:
    if _is_packaged_module(registry, module_name):
        entry = registry_entry_for_module(registry, module_name)
        destination_dir = _vendored_target_dir(app_dir, module_name, entry.metadata)
        if destination_dir == app_dir / "cmake" / "nsx":
            return
        if destination_dir.exists():
            _rmtree(destination_dir)
    else:
        entry = registry_entry_for_module(registry, module_name)
        clone_dir = _module_clone_dir(app_dir, entry.project, registry)
        if clone_dir.exists():
            _rmtree(clone_dir)


def _acquire_modules_for_app(
    app_dir: Path,
    module_names: list[str],
    registry: dict[str, Any],
    *,
    local_modules: set[str] | None = None,
    vendored_modules: set[str] | None = None,
) -> None:
    """Clone or copy all modules needed by an app.

    Modules whose names appear in *local_modules* or *vendored_modules*
    are skipped — they live inside the app tree and are source-controlled
    by the user. (The two sets exist separately so that ``nsx sync`` can
    enforce different invariants on each.)
    """

    skip = (local_modules or set()) | (vendored_modules or set())
    for module_name in module_names:
        if module_name in skip:
            continue
        if _is_packaged_module(registry, module_name):
            _vendor_packaged_module_into_app(app_dir, module_name, registry)
        else:
            _ensure_module_cloned(app_dir, module_name, registry)
