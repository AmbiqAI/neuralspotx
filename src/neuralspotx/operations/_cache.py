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
from pathlib import Path

from .. import module_cache
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
    """Delete every entry in the NSX module artifact cache.

    With ``dry_run=True`` no entries are removed; ``removed_count``
    reflects how many entries *would* be removed.
    """

    root = module_cache.module_cache_root()
    if dry_run:
        return CacheCleanResult(
            root=str(root),
            removed_count=len(module_cache.iter_entries()),
            dry_run=True,
        )
    return CacheCleanResult(
        root=str(root),
        removed_count=module_cache.clear(),
        dry_run=False,
    )
