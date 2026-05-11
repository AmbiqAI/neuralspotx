"""File-tree and git-artifact hashing for ``nsx.lock``."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from ._constants import _ARTIFACT_HASH_CACHE_SCHEMA_VERSION, _HASH_EXCLUDE_DIRS


def _iter_files(root: Path, *, exclude_names: frozenset[str] = frozenset()) -> Iterable[Path]:
    """Yield files under *root*, skipping excluded directories and names."""

    for child in sorted(root.rglob("*")):
        if not child.is_file():
            continue
        rel_parts = child.relative_to(root).parts
        # Skip if any path component is excluded.
        if any(part in _HASH_EXCLUDE_DIRS for part in rel_parts):
            continue
        # Skip top-level files matching exclude_names. Restricted to the
        # top level so a same-named file deeper in the tree is still hashed.
        if len(rel_parts) == 1 and rel_parts[0] in exclude_names:
            continue
        yield child


def hash_tree(root: Path, *, exclude_names: frozenset[str] = frozenset()) -> str:
    """Return a deterministic ``sha256:<hex>`` over the file tree at *root*.

    The hash digests the sorted list of ``(posix-relpath, file-sha256)`` tuples,
    so it is stable across platforms and ignores file metadata.

    *exclude_names* lists top-level filenames to omit from the hash (e.g.
    auto-generated overlay files that are not part of the upstream
    artifact).
    """

    if not root.exists():
        return "sha256:" + hashlib.sha256(b"").hexdigest()

    h = hashlib.sha256()
    for f in _iter_files(root, exclude_names=exclude_names):
        rel = f.relative_to(root).as_posix()
        file_h = hashlib.sha256()
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                file_h.update(chunk)
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(file_h.hexdigest().encode("ascii"))
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


def hash_file(path: Path) -> str:
    """Return ``sha256:<hex>`` of the byte content of a single file."""

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _git_artifact_hash_cache_path() -> Path:
    """Return the path to the persistent ``(url, commit) -> hash`` cache file.

    Honours ``NSX_CACHE_DIR`` if set, else falls back to
    ``$XDG_CACHE_HOME/nsx`` or ``~/.cache/nsx``. The cache is a flat
    JSON object keyed by ``"<url>@<commit>"``; entries are
    immutable (a content hash never changes for a given commit), so
    no eviction is needed.
    """

    override = os.environ.get("NSX_CACHE_DIR")
    if override:
        base = Path(override).expanduser()
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
        base = base / "nsx"
    return base / "git-artifact-hashes.json"


def _read_artifact_hash_cache() -> dict[str, str]:
    """Load the on-disk ``(url@commit) -> hash`` cache.

    File layout (v1):

        {"schema_version": 1, "entries": {"<url>@<commit>": "sha256:..."}}

    A legacy flat-mapping layout (no ``schema_version`` key — every key
    is a cache entry) is also accepted and treated as v1 so existing
    user caches don't have to be discarded by this upgrade.

    Any cache file with a higher ``schema_version`` than this version
    of nsx supports surfaces as a typed :class:`NSXCacheError` so the
    user gets actionable remediation rather than a silent reset.
    """

    path = _git_artifact_hash_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    sv = data.get("schema_version")
    if sv is None:
        # Legacy layout: the entire mapping is the entries dict.
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    if not isinstance(sv, int) or isinstance(sv, bool) or sv < 1:
        # Unparseable header — treat as if absent so a future writer can
        # overwrite without compounding the corruption.
        return {}
    if sv > _ARTIFACT_HASH_CACHE_SCHEMA_VERSION:
        from .._errors import NSXCacheError

        raise NSXCacheError(
            f"{path}: cache schema_version={sv} is newer than this nsx "
            f"supports (v{_ARTIFACT_HASH_CACHE_SCHEMA_VERSION}). "
            "Run `nsx cache clean` (or remove the file) and retry."
        )

    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return {k: v for k, v in entries.items() if isinstance(k, str) and isinstance(v, str)}


def _write_artifact_hash_cache(cache: dict[str, str]) -> None:
    path = _git_artifact_hash_cache_path()
    payload = {
        "schema_version": _ARTIFACT_HASH_CACHE_SCHEMA_VERSION,
        "entries": cache,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write with a unique temp filename so concurrent
        # writers don't clobber each other's tmp file. The final
        # ``replace()`` is atomic on POSIX and Windows for same-fs
        # paths; the last-writer-wins outcome is fine because cache
        # entries are content-addressed and immutable.
        import tempfile

        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, sort_keys=True, indent=2)
            os.replace(tmp_name, path)
        except Exception:
            # Best-effort cleanup of the temp file on any failure.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError:
        # Cache is best-effort: a failure to persist must not break
        # the lock operation.
        pass


def hash_git_artifact(url: str, commit: str, *, use_cache: bool = True) -> str:
    """Hash the working tree at *commit* of the repo at *url*.

    Clones the repo into a tempdir at the exact commit, strips ``.git``,
    and returns :func:`hash_tree` of the result. This is the
    upstream-artifact integrity hash for ``kind=git`` lock entries: it
    records what the user *would* get if they re-vendored, independent
    of whether the module is currently materialized under
    ``modules/<name>/``.

    Used by ``nsx lock`` to compute and record the upstream-artifact
    integrity hash for ``kind=git`` entries. Other callers may use it
    to compare a remote git artifact against the value stored in
    ``nsx.lock``. The clone is discarded.

    Caching: ``(url, commit) -> hash`` is content-addressed and
    immutable, so results are persisted to a user cache file
    (``~/.cache/nsx/git-artifact-hashes.json`` by default; override
    with ``NSX_CACHE_DIR``) and reused across processes. Pass
    ``use_cache=False`` to force a fresh clone-and-hash. Callers that
    invoke this many times in one run should also memoize within the
    process to avoid the JSON round-trip.
    """

    cache_key = f"{url}@{commit}"
    if use_cache:
        cache = _read_artifact_hash_cache()
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    # Imported lazily to avoid a circular import at module load time
    # (subprocess_utils is a leaf, but git_clone_at_commit pulls in tool
    # detection that some tests stub out).
    import tempfile

    from ..subprocess_utils import git_clone_at_commit

    with tempfile.TemporaryDirectory(prefix="nsx-lock-") as tmp:
        clone_dir = Path(tmp) / "clone"
        git_clone_at_commit(url, clone_dir, commit)
        git_dir = clone_dir / ".git"
        if git_dir.exists():
            # Strip metadata so the hash is over the working tree only,
            # matching what _vendor_git_module_at_commit() leaves on disk.
            import shutil

            shutil.rmtree(git_dir, ignore_errors=True)
        result = hash_tree(clone_dir)

    if use_cache:
        from ..file_lock import file_mutex

        cache_path = _git_artifact_hash_cache_path()
        lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
        try:
            with file_mutex(lock_path):
                cache = _read_artifact_hash_cache()
                cache[cache_key] = result
                _write_artifact_hash_cache(cache)
        except OSError:
            # Best-effort: fall back to an unsynchronised RMW. Cache
            # entries are content-addressed and immutable per key, so
            # a lost update only costs a future re-clone.
            cache = _read_artifact_hash_cache()
            cache[cache_key] = result
            _write_artifact_hash_cache(cache)
    return result
