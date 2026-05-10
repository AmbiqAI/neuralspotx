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
compose these primitives.
"""

from __future__ import annotations

import datetime as _dt
import enum
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from ._logging import get_logger
from .subprocess_utils import run_capture

_log = get_logger(__name__)

LOCK_FILENAME = "nsx.lock"
LOCK_SCHEMA_VERSION = 3

# Files/dirs to exclude when hashing a vendored module tree.
_HASH_EXCLUDE_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".DS_Store"})

# Auto-generated overlays written into ``app_dir/cmake/nsx/`` by
# ``_write_app_module_file`` after ``_copy_packaged_tree``. These files
# are not part of the packaged ``nsx-tooling`` wheel resource and must
# be excluded when hashing the materialized tree, otherwise every app
# produces a different content hash purely because of its own
# ``NSX_APP_MODULES`` list.
NSX_TOOLING_AUTOGEN_FILES = frozenset({"modules.cmake"})


# ---------------------------------------------------------------------------
# Lock kind enum
# ---------------------------------------------------------------------------


class LockKind(str, enum.Enum):
    """Resolution kind for a single lock entry.

    Mixed with ``str`` so existing code that compares ``entry.kind ==
    "git"`` keeps working unchanged. New code should prefer the enum
    members (``LockKind.GIT``) for static checking and refactor safety.
    """

    GIT = "git"
    PACKAGED = "packaged"
    LOCAL = "local"
    VENDORED = "vendored"
    UNRESOLVED = "unresolved"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


# Public, hashable set of valid kind strings, useful for parser
# validation without depending on the enum API.
LOCK_KINDS: frozenset[str] = frozenset(k.value for k in LockKind)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResolvedModule:
    """Resolution record for one module."""

    project: str
    kind: LockKind
    constraint: str
    vendored_at: str
    content_hash: str
    acquired_at: str
    url: str | None = None
    tag: str | None = None
    commit: str | None = None
    tool_version: str | None = None

    def to_yaml_dict(self) -> dict[str, Any]:
        resolved: dict[str, Any] = {
            "vendored_at": self.vendored_at,
            "content_hash": self.content_hash,
            "acquired_at": self.acquired_at,
        }
        if self.kind in (LockKind.GIT, LockKind.UNRESOLVED):
            head: dict[str, Any] = {"url": self.url}
            if self.tag:
                head["tag"] = self.tag
            head["commit"] = self.commit
            resolved = {**head, **resolved}
        elif self.kind == LockKind.PACKAGED and self.tool_version:
            resolved = {"tool_version": self.tool_version, **resolved}
        return {
            "project": self.project,
            "kind": str(self.kind),
            "constraint": self.constraint,
            "resolved": resolved,
        }

    @classmethod
    def from_yaml_dict(cls, name: str, data: dict[str, Any]) -> "ResolvedModule":
        if not isinstance(data, dict):
            raise ValueError(f"Invalid lock entry for module '{name}'")
        resolved = data.get("resolved") or {}
        raw_kind = data.get("kind", "git")
        try:
            kind = LockKind(raw_kind)
        except ValueError:
            kind = LockKind.GIT  # graceful fallback for unknown kinds
        return cls(
            project=data.get("project", ""),
            kind=kind,
            constraint=str(data.get("constraint", "")),
            vendored_at=resolved.get("vendored_at", ""),
            content_hash=resolved.get("content_hash", ""),
            acquired_at=resolved.get("acquired_at", ""),
            url=resolved.get("url"),
            tag=resolved.get("tag"),
            commit=resolved.get("commit"),
            tool_version=resolved.get("tool_version"),
        )


@dataclass
class NsxLock:
    """Top-level nsx.lock document."""

    schema_version: int = LOCK_SCHEMA_VERSION
    generated_at: str = ""
    nsx_tool_version: str | None = None
    manifest_path: str = "nsx.yml"
    manifest_hash: str = ""
    target: dict[str, str] = field(default_factory=dict)
    modules: dict[str, ResolvedModule] = field(default_factory=dict)
    # Filesystem path to ``nsx.lock`` on disk. Populated by ``read_lock``
    # and ``write_lock``; ``None`` for in-memory documents that have not
    # yet been persisted. Excluded from equality, repr and YAML
    # serialisation so it cannot leak back into the on-disk document.
    path: Path | None = field(default=None, compare=False, repr=False)

    def to_yaml_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "nsx_tool": {"version": self.nsx_tool_version},
            "manifest": {"path": self.manifest_path, "hash": self.manifest_hash},
            "target": self.target,
            "modules": {name: entry.to_yaml_dict() for name, entry in sorted(self.modules.items())},
        }

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "NsxLock":
        if not isinstance(data, dict):
            raise ValueError("nsx.lock root must be a mapping")
        version = int(data.get("schema_version", LOCK_SCHEMA_VERSION))
        if version != LOCK_SCHEMA_VERSION:
            raise LegacyLockError(
                f"nsx.lock has schema_version {version}; this nsx requires "
                f"v{LOCK_SCHEMA_VERSION}. Run `nsx lock` to regenerate."
            )
        nsx_tool = data.get("nsx_tool") or {}
        manifest = data.get("manifest") or {}
        modules_raw = data.get("modules") or {}
        modules: dict[str, ResolvedModule] = {}
        for name, entry in modules_raw.items():
            modules[name] = ResolvedModule.from_yaml_dict(name, entry)
        return cls(
            schema_version=version,
            generated_at=str(data.get("generated_at", "")),
            nsx_tool_version=nsx_tool.get("version"),
            manifest_path=str(manifest.get("path", "nsx.yml")),
            manifest_hash=str(manifest.get("hash", "")),
            target=dict(data.get("target") or {}),
            modules=modules,
        )


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def lock_path(app_dir: Path) -> Path:
    return app_dir / LOCK_FILENAME


def read_lock(app_dir: Path, *, allow_legacy: bool = False) -> NsxLock | None:
    """Read nsx.lock from *app_dir*, or return ``None`` if missing.

    If the file exists but uses a schema older than
    :data:`LOCK_SCHEMA_VERSION`, behaviour depends on *allow_legacy*:

    * ``False`` (default): raise :class:`LegacyLockError` so callers like
      ``nsx sync`` / ``nsx outdated`` fail loudly with the upgrade hint.
    * ``True``: emit a one-line warning and return ``None`` so callers
      like ``nsx lock`` can transparently regenerate the file in place.
    """

    path = lock_path(app_dir)
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        lock = NsxLock.from_yaml_dict(raw or {})
    except LegacyLockError as exc:
        if allow_legacy:
            _log.warning("%s (regenerating)", exc)
            return None
        raise
    lock.path = path
    return lock


def write_lock(app_dir: Path, lock: NsxLock) -> Path:
    """Write *lock* to ``<app_dir>/nsx.lock`` atomically and return the path.

    Writes through a same-directory temp file + ``os.replace`` so a
    crash or Ctrl-C mid-write cannot leave a half-written ``nsx.lock``
    on disk. ``os.replace`` is atomic on POSIX and Windows when both
    paths are on the same filesystem (guaranteed here because the temp
    file lives next to the target).
    """

    import tempfile

    path = lock_path(app_dir)
    text = yaml.safe_dump(lock.to_yaml_dict(), sort_keys=False, default_flow_style=False)
    header = (
        "# nsx.lock — generated by `nsx lock`. Do not edit by hand.\n"
        "# Commit this file to record the resolved module set for this app.\n"
    )
    payload = (header + text).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                # fsync can fail on some filesystems (e.g. tmpfs in
                # CI); the os.replace below is still atomic.
                pass
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    lock.path = path
    return path


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


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
    path = _git_artifact_hash_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _write_artifact_hash_cache(cache: dict[str, str]) -> None:
    path = _git_artifact_hash_cache_path()
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
                json.dump(cache, fh, sort_keys=True, indent=2)
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

    from .subprocess_utils import git_clone_at_commit

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
        from .file_lock import file_mutex

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


# ---------------------------------------------------------------------------
# Git resolution
# ---------------------------------------------------------------------------


def resolve_commit(url: str, ref: str) -> str:
    """Resolve *ref* (branch/tag/SHA) on remote *url* to a 40-char SHA.

    Uses ``git ls-remote`` so no clone is needed. If *ref* already looks
    like a full 40-char SHA, it is returned as-is. For annotated tags,
    the **peeled** commit (``refs/tags/<x>^{}``) is preferred over the
    tag-object SHA, so the recorded commit is what ``git checkout <tag>``
    would actually land on. Raises :class:`ResolutionError` if the
    remote is unreachable or the ref is not found.
    """

    if _looks_like_full_sha(ref):
        return ref.lower()

    sha, _matched = resolve_ref(url, ref)
    return sha


def resolve_ref(url: str, ref: str, *, bypass_cache: bool = False) -> tuple[str, str | None]:
    """Resolve *ref* and report what kind of upstream ref it matched.

    Returns ``(sha, matched_kind)`` where ``matched_kind`` is one of
    ``"tag"``, ``"branch"``, ``"sha"`` or ``None``. ``sha`` is always
    the underlying commit SHA (annotated tags are peeled).

    Results are cached on-disk for ``NSX_RESOLVE_TTL`` seconds (default
    300).  Set ``bypass_cache=True`` (e.g. ``nsx lock --update``) to
    force a fresh ``git ls-remote``.
    """

    if _looks_like_full_sha(ref):
        return ref.lower(), "sha"

    if not bypass_cache:
        from . import _resolve_cache

        cached = _resolve_cache.get(url, ref)
        if cached is not None:
            return cached

    result = _resolve_ref(url, ref)

    from . import _resolve_cache

    _resolve_cache.put(url, ref, result[0], result[1])
    return result


def _resolve_ref(url: str, ref: str) -> tuple[str, str | None]:
    # Pass both `<ref>` and `<ref>^{}` so annotated tags return both
    # the tag-object line and the peeled-commit line. Branches and
    # lightweight tags only return one line; the `^{}` query is a no-op.
    try:
        result = run_capture(["git", "ls-remote", url, ref, f"{ref}^{{}}"])
    except subprocess.CalledProcessError as exc:
        raise ResolutionError(
            f"git ls-remote failed for {url} @ {ref}: exit {exc.returncode}"
        ) from exc

    tag_sha: str | None = None
    peeled_sha: str | None = None
    branch_sha: str | None = None
    other_sha: str | None = None

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, name = line.partition("\t")
        sha = sha.strip()
        if not sha:
            continue
        if name == f"refs/tags/{ref}^{{}}":
            peeled_sha = sha
        elif name == f"refs/tags/{ref}":
            tag_sha = sha
        elif name == f"refs/heads/{ref}":
            branch_sha = sha
        elif name == ref and other_sha is None:
            other_sha = sha

    if peeled_sha:
        # Annotated tag: peeled commit is what `git checkout <tag>` lands on.
        return peeled_sha, "tag"
    if tag_sha:
        # Lightweight tag (no separate tag object): tag SHA *is* the commit.
        return tag_sha, "tag"
    if branch_sha:
        return branch_sha, "branch"
    if other_sha:
        return other_sha, None
    raise ResolutionError(f"Unable to resolve revision '{ref}' on {url}")


class ResolutionError(RuntimeError):
    """Raised when a git remote cannot be resolved during ``nsx lock``."""


class LegacyLockError(RuntimeError):
    """Raised when ``nsx.lock`` uses an older schema version.

    ``read_lock(..., allow_legacy=True)`` swallows this so ``nsx lock``
    can rewrite the file in place; everywhere else it propagates and is
    surfaced to the user as a clear migration message.
    """


def _looks_like_full_sha(s: str) -> bool:
    return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)


# ---------------------------------------------------------------------------
# Manifest hashing (for drift detection)
# ---------------------------------------------------------------------------


def hash_manifest(nsx_yml_path: Path) -> str:
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
