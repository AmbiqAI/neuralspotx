"""NSX module artifact cache operations.

These helpers back the public ``api.cache_info()`` and
``api.clean_cache()`` entry points and the ``nsx cache info`` /
``nsx cache clean`` CLI commands. They are purely functional — they
never write to stdout — so embedders can introspect the result via
the typed :class:`~neuralspotx.models.CacheInfo` and
:class:`~neuralspotx.models.CacheCleanResult` dataclasses.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .. import module_cache
from .._cache_paths import nsx_cache_root
from ..models import CacheCleanResult, CacheEntry, CacheInfo


def _dir_size_bytes(path: Path) -> int:
    """Best-effort recursive size of *path* in bytes (silently skips errors)."""

    total = 0
    for root, _dirs, files in os.walk(path):
        for fname in files:
            fpath = Path(root) / fname
            try:
                total += fpath.stat().st_size
            except OSError:
                continue
    return total


def cache_info_impl() -> CacheInfo:
    """Return a snapshot of the NSX module artifact cache."""

    root = module_cache.module_cache_root()
    raw_entries = module_cache.iter_entries()
    entries = tuple(
        CacheEntry(
            digest=f"{e.parent.name}{e.name}",
            path=str(e),
            size_bytes=_dir_size_bytes(e),
        )
        for e in raw_entries
    )
    return CacheInfo(
        root=str(root),
        disabled=module_cache.is_disabled(),
        entries=entries,
    )


def clean_cache_impl(*, dry_run: bool = False) -> CacheCleanResult:
    """Delete every neuralSPOT-X persistent cache.

    With ``dry_run=True`` no entries are removed; ``removed_count``
    reflects how many entries *would* be removed.
    """

    root = nsx_cache_root()
    module_root = module_cache.module_cache_root()
    module_entries = len(module_cache.iter_entries())
    module_count = module_entries or int(module_root.exists() or module_root.is_symlink())
    cache_files = (
        # v1/legacy path, retained here so cleanup migrates old installations.
        root / "git-artifact-hashes.json",
        root / "git-artifact-hashes.json.lock",
        root / "git-artifact-hashes-v2.json",
        root / "git-artifact-hashes-v2.json.lock",
        root / "resolve-ref-cache.json",
        root / "resolve-ref-cache.json.lock",
    )
    file_count = sum(path.exists() or path.is_symlink() for path in cache_files)
    if dry_run:
        return CacheCleanResult(
            root=str(root),
            removed_count=module_count + file_count,
            dry_run=True,
        )
    removed = module_cache.clear()
    for path in cache_files:
        existed = path.exists() or path.is_symlink()
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            continue
        if existed and not path.exists() and not path.is_symlink():
            removed += 1
    return CacheCleanResult(
        root=str(root),
        removed_count=removed,
        dry_run=False,
    )
