"""Persistent TTL-based cache for ``git ls-remote`` (resolve_ref) results.

Speeds up repeated ``nsx lock`` invocations — e.g. when helia-profiler
profiles multiple models in sequence and the module constraints haven't
changed between runs.

Cache file: ``$NSX_CACHE_DIR/resolve-ref-cache.json``  (same base as
``git-artifact-hashes.json``).

Configuration (env vars):
    NSX_RESOLVE_TTL   Seconds that a cached ``(url, ref) -> (sha, kind)``
                      entry is considered fresh.  Default: 300 (5 min).
                      Set to ``0`` to disable the cache entirely.
                      Set to a large value (e.g. 1800 for 30 min) for
                      long-running automated workflows.

The cache is **bypassed** when ``nsx lock --update`` is used — that
flag means "go to the network and re-resolve everything".
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

from ._cache_paths import nsx_cache_root

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ENV_TTL = "NSX_RESOLVE_TTL"
_DEFAULT_TTL: float = 300.0  # 5 minutes

# Per-call override that takes precedence over the env var. Scoped via
# ``ttl_override`` context manager so concurrent callers can set their
# own TTL without mutating process-global ``os.environ``.
_ttl_override: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "nsx_resolve_ttl_override", default=None
)


def _ttl_seconds() -> float:
    """Return the configured TTL; 0 means cache disabled.

    Resolution order: contextvar override (set by :func:`ttl_override`),
    then ``NSX_RESOLVE_TTL`` env var, then the built-in default.
    """
    override = _ttl_override.get()
    if override is not None:
        return max(float(override), 0.0)
    raw = os.environ.get(_ENV_TTL)
    if raw is None:
        return _DEFAULT_TTL
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return _DEFAULT_TTL
    return max(val, 0.0)


@contextlib.contextmanager
def ttl_override(seconds: float | None) -> Iterator[None]:
    """Temporarily override the resolve-cache TTL for the current context.

    Pass ``None`` to keep the existing behaviour (env var / default).
    Pass ``0`` to disable the cache for the duration of the block.
    Safe under concurrent callers: implemented with ``ContextVar`` so
    overrides do not leak between threads or async tasks.
    """

    if seconds is None:
        yield
        return
    token = _ttl_override.set(float(seconds))
    try:
        yield
    finally:
        _ttl_override.reset(token)


# ---------------------------------------------------------------------------
# Cache path (shares $NSX_CACHE_DIR with git-artifact-hashes.json)
# ---------------------------------------------------------------------------


def _cache_path() -> Path:
    return nsx_cache_root() / "resolve-ref-cache.json"


# ---------------------------------------------------------------------------
# Serialization: { "<url>\t<ref>": [sha, kind_or_null, timestamp_float] }
# ---------------------------------------------------------------------------

_CacheEntry = tuple[str, str | None, float]  # (sha, kind, ts)


def _read_cache() -> dict[str, _CacheEntry]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, _CacheEntry] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, list) or len(v) != 3:
            continue
        sha, kind, ts = v
        if not isinstance(sha, str) or not isinstance(ts, (int, float)):
            continue
        out[k] = (sha, kind if isinstance(kind, str) else None, float(ts))
    return out


def _write_cache(entries: dict[str, _CacheEntry]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(
                    {k: list(v) for k, v in entries.items()},
                    fh,
                    sort_keys=True,
                )
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def _cache_key(url: str, ref: str) -> str:
    return f"{url}\t{ref}"


def get(url: str, ref: str) -> tuple[str, str | None] | None:
    """Look up a cached resolve result.  Returns ``None`` on miss/expired."""
    ttl = _ttl_seconds()
    if ttl == 0:
        return None
    key = _cache_key(url, ref)
    entries = _read_cache()
    entry = entries.get(key)
    if entry is None:
        return None
    sha, kind, ts = entry
    if (time.time() - ts) > ttl:
        return None
    return sha, kind


def put(url: str, ref: str, sha: str, kind: str | None) -> None:
    """Store a resolve result with the current timestamp.

    Serialises read-modify-write under a sidecar file lock so concurrent
    ``nsx`` processes can't drop each other's entries (last-writer-wins
    on the full JSON snapshot would otherwise lose updates).
    """
    ttl = _ttl_seconds()
    if ttl == 0:
        return
    key = _cache_key(url, ref)

    from .file_lock import file_mutex

    lock_path = _cache_path().with_suffix(_cache_path().suffix + ".lock")
    try:
        with file_mutex(lock_path):
            entries = _read_cache()
            # Prune stale entries while we're at it.
            now = time.time()
            entries = {k: v for k, v in entries.items() if (now - v[2]) < ttl}
            entries[key] = (sha, kind, now)
            _write_cache(entries)
    except OSError:
        # Cache is best-effort; if locking the sidecar fails, fall
        # back to an unsynchronised write rather than failing the
        # caller. The atomic ``os.replace`` in ``_write_cache`` still
        # guarantees no torn file.
        entries = _read_cache()
        now = time.time()
        entries = {k: v for k, v in entries.items() if (now - v[2]) < ttl}
        entries[key] = (sha, kind, now)
        _write_cache(entries)


def invalidate_all() -> None:
    """Remove the cache file entirely (used by ``nsx lock --update``)."""
    path = _cache_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
