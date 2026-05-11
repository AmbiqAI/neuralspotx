"""Cache inspection and cleanup."""

from __future__ import annotations

from .. import operations
from ..models import CacheCleanResult, CacheInfo


def cache_info() -> CacheInfo:
    """Return a snapshot of the NSX module artifact cache.

    The result includes the cache root, an "is the cache disabled
    via NSX_DISABLE_MODULE_CACHE" flag, and one
    :class:`~neuralspotx.models.CacheEntry` per content-addressed
    artifact directory. ``CacheInfo.total_size_bytes`` is computed
    by walking each entry — best-effort, errors are silently ignored
    per file. Performs no I/O on stdout.
    """

    return operations.cache_info_impl()


def clean_cache(*, dry_run: bool = False) -> CacheCleanResult:
    """Delete every entry in the NSX module artifact cache.

    With ``dry_run=True`` no entries are removed; the returned
    :class:`~neuralspotx.models.CacheCleanResult.removed_count`
    reflects how many entries *would* be removed by an unconditional
    invocation. Performs no I/O on stdout.
    """

    return operations.clean_cache_impl(dry_run=dry_run)
