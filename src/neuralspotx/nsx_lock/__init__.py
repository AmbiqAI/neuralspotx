"""nsx.lock — resolution receipt for an NSX app.

Phase 1 of the lock/sync system. Records, per app, the exact resolved
git commit and content hash of every vendored module so that builds are
reproducible and `nsx sync` can deterministically restore the modules/
tree.

Schema (YAML, v3):

    schema_version: 3
    generated_at: <ISO 8601 UTC>
    nsx_tool: { version: <pkg version> }
    manifest: { path: nsx.yml, hash: sha256:<hex> }
    target: { board, soc, toolchain }
    modules:
      <module-name>:
        project: <project-key>
        kind: git | packaged | local | vendored | unresolved
        constraint: <revision string from nsx.yml>
        resolved:
          # git only:
          url: <repo url>
          tag: <tag name>           # set when constraint resolved through a tag
          commit: <40-char SHA>     # ALWAYS the underlying commit SHA, not
                                    # the annotated-tag-object SHA
          # all kinds:
          vendored_at: <relpath under app dir>
          content_hash: sha256:<hex>
          acquired_at: <ISO 8601 UTC>
          # packaged only:
          tool_version: <neuralspotx pkg version>

``content_hash`` semantics (v3, cargo/uv-style — hashes the *upstream
artifact*, never the on-disk vendored tree):

    git        — hash of the git working tree at the locked commit
                  (computed by cloning at ``commit`` into a tempdir,
                  stripping ``.git``, and hashing). Independent of
                  whether/how the module is currently vendored under
                  ``modules/``.
    packaged   — hash of the packaged source tree shipped inside the
                  ``neuralspotx`` Python wheel (the registry resource
                  dir).
    local      — if the registry project has a ``local_path``: hash of
                  that source directory. Otherwise (in-tree local, e.g.
                  ``nsx module add --local``): hash of
                  ``modules/<name>/`` itself — the directory IS the
                  source.
    vendored   — hash of ``modules/<name>/`` itself — the directory IS
                  the source (committed in the app).
    unresolved — last-known hash of ``modules/<name>/`` from the
                  previous lock or the current on-disk tree, since
                  upstream is unreachable.

This decoupling means ``nsx lock`` can produce real hashes on a fresh
checkout (no ``modules/`` populated yet) and ``nsx sync`` never needs
to modify the lock to keep it in sync with reality — the lock is
written exactly once per actual change to the upstream resolution.

v3 changes vs v2:
  * ``content_hash`` is now the upstream-artifact hash, not the
    materialized tree hash. Schema-wise the field is identical; the
    bump signals the semantic change so v2 lockfiles are regenerated.

v2 changes vs v1:
  * Drop `ref:` (was always equal to `constraint:`).
  * Add `tag:` — distinct from `constraint:` so we can tell whether the
    constraint resolved via a tag (vs a branch or raw SHA).
  * `commit:` is guaranteed to be the underlying commit SHA. v1 stored
    the annotated-tag-object SHA when the constraint was an annotated
    tag, which broke `git checkout` reproducibility if the tag was
    later force-moved.

No back-compat reads for older schemas: pre-1.0, only one user; old
locks are rejected and the user is told to run ``nsx lock``.

Kinds (the user-facing 'source:' field in nsx.yml maps to a kind):
    git        -> registry git module (default; sync re-clones at locked SHA)
    packaged   -> shipped inside the neuralspotx package (sync re-copies)
    local      -> linked from an external path (legacy ``local: true``)
    vendored   -> source: { vendored: true }  (committed in app; sync hands-off)
    unresolved -> registry module whose upstream was unreachable at lock time
                  (content-only entry; sync verifies hash, can't re-fetch)

Public API kept intentionally small so the CLI/operations layer can
compose these primitives. The module is implemented as a package
(``nsx_lock/``) split into focused submodules; this ``__init__`` is a
facade that re-exports the historical flat API so
``from neuralspotx.nsx_lock import X`` keeps working unchanged.
"""

from __future__ import annotations

import datetime as _dt
import hashlib

import yaml

from .._logging import get_logger
from ._constants import (
    _ARTIFACT_HASH_CACHE_SCHEMA_VERSION,
    _HASH_EXCLUDE_DIRS,
    LOCK_FILENAME,
    LOCK_SCHEMA_VERSION,
    NSX_TOOLING_AUTOGEN_FILES,
)
from ._hashing import (
    _git_artifact_hash_cache_path,
    _iter_files,
    _read_artifact_hash_cache,
    _write_artifact_hash_cache,
    hash_file,
    hash_git_artifact,
    hash_tree,
)
from ._io import lock_path, read_lock, write_lock
from ._kinds import LOCK_KINDS, LockKind
from ._models import NsxLock, ResolvedModule
from ._resolution import (
    ResolutionError,
    _looks_like_full_sha,
    _resolve_ref,
    resolve_commit,
    resolve_ref,
)

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Manifest hashing (for drift detection)
# ---------------------------------------------------------------------------


def hash_manifest(nsx_yml_path):
    """Hash an ``nsx.yml`` file deterministically by re-serializing the parsed YAML.

    This makes the hash stable against whitespace/comment changes that
    do not affect the parsed manifest.
    """

    if not nsx_yml_path.exists():
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    parsed = yaml.safe_load(nsx_yml_path.read_text(encoding="utf-8")) or {}
    canonical = yaml.safe_dump(parsed, sort_keys=True, default_flow_style=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def utcnow_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


__all__ = [
    "LOCK_FILENAME",
    "LOCK_KINDS",
    "LOCK_SCHEMA_VERSION",
    "LockKind",
    "NSX_TOOLING_AUTOGEN_FILES",
    "NsxLock",
    "ResolutionError",
    "ResolvedModule",
    "hash_file",
    "hash_git_artifact",
    "hash_manifest",
    "hash_tree",
    "lock_path",
    "read_lock",
    "resolve_commit",
    "resolve_ref",
    "utcnow_iso",
    "write_lock",
    # Internals re-exported for tests / other neuralspotx submodules.
    "_ARTIFACT_HASH_CACHE_SCHEMA_VERSION",
    "_HASH_EXCLUDE_DIRS",
    "_git_artifact_hash_cache_path",
    "_iter_files",
    "_looks_like_full_sha",
    "_read_artifact_hash_cache",
    "_resolve_ref",
    "_write_artifact_hash_cache",
]
