"""Content-addressed cache of vendored module artifacts.

Background
----------
``nsx sync`` materialises each ``kind=git`` lock entry by performing a
fresh ``git_clone_at_commit`` into ``modules/<name>/`` and stripping
``.git`` (see :func:`module_registry._vendor_git_module_at_commit`).
Because hpx (and CI) typically run ``nsx sync`` against fresh
work directories, the same ``(url, commit)`` is re-cloned over and
over even though its content is immutable.

This module adds an opt-in, content-addressed cache that stores a
copy of the stripped working tree under
``$NSX_CACHE_DIR/modules/<digest[:2]>/<digest[2:]>/`` keyed by the
artifact's ``content_hash`` — the same hash already recorded in
``nsx.lock`` for ``kind=git`` entries (see
:func:`nsx_lock.hash_git_artifact`).

A cache hit lets ``_vendor_git_module_at_commit`` skip the network
round-trip entirely and just ``copytree`` the cached entry into
``modules/<name>/``.

Cache layout::

    $NSX_CACHE_DIR/
        git-artifact-hashes.json     (existing)
        modules/
            <aa>/<bbbbbb...>/         <- cache entry; mirror of stripped
                                         working tree (no .git)
            ...

Where ``aa`` is the first two hex chars of the digest and ``bbbbbb...``
is the rest, matching the convention used by git's loose-object store
and most other content-addressed systems.

Environment variables
---------------------
- ``NSX_CACHE_DIR`` — base directory for nsx caches. Defaults to
  ``$XDG_CACHE_HOME/nsx`` or ``~/.cache/nsx``.
- ``NSX_DISABLE_MODULE_CACHE`` — set to ``1``/``true``/``yes``/``on``
  to bypass the cache entirely (always clone, never read or write the
  cache). Useful for diagnosing suspected drift.

Safety
------
- Entries are immutable: a content hash never changes for a given
  commit, so no eviction is needed.
- Cache writes are *atomic*: the populating process writes to a unique
  ``<digest>.tmp.<pid>.<rand>/`` directory next to the target and
  ``os.replace()``s it into place. Concurrent populators race
  harmlessly — the loser's tmp dir is removed.
- Reads are tolerant: a corrupted entry (e.g. interrupted populate
  that left a non-atomic state) is detected at copy time and treated
  as a miss; the corrupted dir is removed and a fresh clone proceeds.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

__all__ = [
    "InvalidContentHashError",
    "module_cache_root",
    "cache_entry_for_hash",
    "lookup",
    "populate",
    "is_disabled",
    "iter_entries",
    "clear",
]


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _nsx_cache_root() -> Path:
    """Return the base nsx cache directory (parent of ``modules/``).

    Mirrors :func:`nsx_lock._git_artifact_hash_cache_path`'s resolution
    so both caches live in the same root.
    """

    override = os.environ.get("NSX_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "nsx"


def module_cache_root() -> Path:
    """Return the directory under which all module artifact entries live."""

    return _nsx_cache_root() / "modules"


_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]+$")


class InvalidContentHashError(ValueError):
    """Raised when a ``content_hash`` is not a safe hex digest."""


def _digest_from_content_hash(content_hash: str) -> str:
    """Strip the ``"sha256:"`` prefix and validate the digest.

    The returned digest is guaranteed to match ``[0-9a-f]+`` so it is
    safe to interpolate into a filesystem path. Lockfile values are
    treated as untrusted input, so a crafted entry like
    ``sha256:../../etc`` is rejected up front and cannot escape
    :func:`module_cache_root`.
    """

    raw = content_hash.split(":", 1)[1] if ":" in content_hash else content_hash
    digest = raw.strip().lower()
    if not digest or not _HEX_DIGEST_RE.match(digest):
        raise InvalidContentHashError(f"content_hash must be a hex digest (got {content_hash!r})")
    return digest


def cache_entry_for_hash(content_hash: str) -> Path:
    """Resolve the cache directory for a given ``content_hash``.

    The returned path may or may not exist — callers should use
    :func:`lookup` to test for cache hits.

    Raises :class:`InvalidContentHashError` if ``content_hash`` is not
    a hex digest. This prevents path-traversal via crafted lockfile
    values (the digest is interpolated into the cache filesystem path).
    """

    digest = _digest_from_content_hash(content_hash)
    if len(digest) < 4:
        # Pathological digest; bucket under "_" to keep the layout sane.
        return module_cache_root() / "_" / digest
    return module_cache_root() / digest[:2] / digest[2:]


# ---------------------------------------------------------------------------
# Disable switch
# ---------------------------------------------------------------------------


_TRUTHY = {"1", "true", "yes", "on"}


def is_disabled() -> bool:
    """Whether the cache should be bypassed entirely (env-controlled)."""

    return os.environ.get("NSX_DISABLE_MODULE_CACHE", "").strip().lower() in _TRUTHY


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def lookup(content_hash: str, dest: Path) -> bool:
    """Try to materialise *content_hash* into *dest*.

    Returns ``True`` if the cache had a usable entry and *dest* is
    populated; ``False`` on cache miss (or when the cache is disabled).
    Any pre-existing content at *dest* is replaced on hit.

    A copy is performed (not a symlink) so callers can mutate
    ``modules/<name>/`` without polluting the cache. Symlinks within
    the cached tree are preserved.
    """

    if is_disabled():
        return False

    try:
        src = cache_entry_for_hash(content_hash)
    except InvalidContentHashError:
        # Untrusted lockfile entry; treat as a miss so the caller
        # falls back to a fresh clone (and any subsequent populate()
        # will be a no-op for the same reason).
        return False
    if not src.is_dir():
        return False

    # Replace dest atomically-enough for our purposes: the prior
    # contents may have been a partial clone from a failed previous
    # run, so blow it away first.
    try:
        if dest.exists():
            _rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, symlinks=True)
    except (OSError, shutil.Error):
        # Cached entry is unreadable / partial. Treat as miss; the
        # caller will fall back to a fresh clone, and a subsequent
        # successful populate() will overwrite the bad entry.
        try:
            if dest.exists():
                _rmtree(dest)
        except OSError:
            pass
        try:
            _rmtree(src)
        except OSError:
            pass
        return False

    return True


def populate(content_hash: str, source: Path) -> None:
    """Copy *source* into the cache under *content_hash*.

    Idempotent and concurrency-safe: if another process populated the
    same entry first, our copy is discarded. Failures are swallowed —
    the cache is best-effort and must never break ``nsx sync``.

    *source* must be a fully-materialised, ``.git``-stripped working
    tree (i.e. exactly what ``modules/<name>/`` should look like).
    """

    if is_disabled():
        return
    if not source.is_dir():
        return

    try:
        target = cache_entry_for_hash(content_hash)
    except InvalidContentHashError:
        # Refuse to write outside the cache root.
        return
    if target.exists():
        # Already cached (by us on a prior run, or by a concurrent
        # populator). Nothing to do.
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    # Copy into a sibling tmpdir, then rename atomically. ``mkdtemp``
    # gives us a unique name even under heavy parallelism.
    try:
        tmp = Path(tempfile.mkdtemp(prefix=target.name + ".tmp.", dir=target.parent))
    except OSError:
        return

    try:
        # ``dirs_exist_ok=False`` because mkdtemp returned an empty dir
        # and we want to fail loudly if anything else is in there. We
        # copy *into* tmp so the final layout is tmp/<files> rather
        # than tmp/<source-name>/<files>; achieve that by removing tmp
        # first and treating it as the destination for copytree.
        shutil.rmtree(tmp)
        shutil.copytree(source, tmp, symlinks=True)
        os.replace(tmp, target)
    except OSError:
        # Race: a concurrent populator beat us. ``os.replace`` onto a
        # non-empty directory fails on POSIX; treat as success.
        if target.is_dir():
            try:
                _rmtree(tmp)
            except OSError:
                pass
            return
        # Other OSError — give up silently; cache is best-effort.
        try:
            _rmtree(tmp)
        except OSError:
            pass
    except shutil.Error:
        try:
            _rmtree(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Maintenance helpers (used by ``nsx cache`` CLI)
# ---------------------------------------------------------------------------


def iter_entries() -> list[Path]:
    """Return a list of every cache entry directory currently on disk."""

    root = module_cache_root()
    if not root.is_dir():
        return []
    out: list[Path] = []
    for shard in sorted(root.iterdir()):
        if not shard.is_dir():
            continue
        for entry in sorted(shard.iterdir()):
            if entry.is_dir() and not entry.name.startswith(".") and ".tmp." not in entry.name:
                out.append(entry)
    return out


def clear() -> int:
    """Delete every entry under the module cache.

    Returns the number of entries removed. The cache root itself is
    left in place so subsequent ``populate()`` calls don't need to
    recreate it.
    """

    root = module_cache_root()
    if not root.is_dir():
        return 0
    removed = 0
    for shard in list(root.iterdir()):
        if not shard.is_dir():
            continue
        for entry in list(shard.iterdir()):
            try:
                _rmtree(entry)
                removed += 1
            except OSError:
                pass
        try:
            shard.rmdir()
        except OSError:
            pass
    return removed


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _on_rm_error(_func, _path, _exc_info):  # noqa: ANN001
    # Mirror the resilience of module_registry._rmtree: clear the
    # write bit and retry. Pack files written by git can be read-only
    # on Windows even though we strip ``.git`` afterwards, and any
    # leftover .tmp.<pid> directory may have similar permissions.
    import stat as _stat

    try:
        os.chmod(_path, _stat.S_IWRITE)
    except OSError:
        pass
    # Retry the failing op. On Python 3.12+ shutil.rmtree uses fd-based
    # syscalls (e.g. ``os.open(path, flags)``) which require multiple
    # positional args; calling ``_func(_path)`` then raises TypeError.
    # Swallow it -- the next rmtree pass will retry the parent.
    try:
        _func(_path)
    except (OSError, TypeError):
        pass


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_on_rm_error)
