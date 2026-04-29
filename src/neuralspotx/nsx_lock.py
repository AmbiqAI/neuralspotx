"""nsx.lock — resolution receipt for an NSX app.

Phase 1 of the lock/sync system. Records, per app, the exact resolved
git commit and content hash of every vendored module so that builds are
reproducible and `nsx sync` can deterministically restore the modules/
tree.

Schema (YAML, v2):

    schema_version: 2
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

v2 changes vs v1:
  * Drop `ref:` (was always equal to `constraint:`).
  * Add `tag:` — distinct from `constraint:` so we can tell whether the
    constraint resolved via a tag (vs a branch or raw SHA).
  * `commit:` is guaranteed to be the underlying commit SHA. v1 stored
    the annotated-tag-object SHA when the constraint was an annotated
    tag, which broke `git checkout` reproducibility if the tag was
    later force-moved.

No v1 read compat: schemas before v2 raise on load and direct the user
to regenerate via `nsx lock`. (Pre-1.0; only one user.)

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
import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .subprocess_utils import run_capture

LOCK_FILENAME = "nsx.lock"
LOCK_SCHEMA_VERSION = 2

# Files/dirs to exclude when hashing a vendored module tree.
_HASH_EXCLUDE_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".DS_Store"})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResolvedModule:
    """Resolution record for one module."""

    project: str
    kind: str  # "git" | "packaged" | "local" | "vendored" | "unresolved"
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
        if self.kind in ("git", "unresolved"):
            head: dict[str, Any] = {"url": self.url}
            if self.tag:
                head["tag"] = self.tag
            head["commit"] = self.commit
            resolved = {**head, **resolved}
        elif self.kind == "packaged" and self.tool_version:
            resolved = {"tool_version": self.tool_version, **resolved}
        return {
            "project": self.project,
            "kind": self.kind,
            "constraint": self.constraint,
            "resolved": resolved,
        }

    @classmethod
    def from_yaml_dict(cls, name: str, data: dict[str, Any]) -> "ResolvedModule":
        if not isinstance(data, dict):
            raise ValueError(f"Invalid lock entry for module '{name}'")
        resolved = data.get("resolved") or {}
        return cls(
            project=data.get("project", ""),
            kind=data.get("kind", "git"),
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
        return NsxLock.from_yaml_dict(raw or {})
    except LegacyLockError as exc:
        if allow_legacy:
            print(f"warning: {exc} (regenerating)")
            return None
        raise


def write_lock(app_dir: Path, lock: NsxLock) -> Path:
    """Write *lock* to ``<app_dir>/nsx.lock`` and return the path."""

    path = lock_path(app_dir)
    text = yaml.safe_dump(lock.to_yaml_dict(), sort_keys=False, default_flow_style=False)
    header = (
        "# nsx.lock — generated by `nsx lock`. Do not edit by hand.\n"
        "# Commit this file to record the resolved module set for this app.\n"
    )
    path.write_text(header + text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _iter_files(root: Path) -> Iterable[Path]:
    """Yield files under *root*, skipping excluded directories."""

    for child in sorted(root.rglob("*")):
        if not child.is_file():
            continue
        # Skip if any path component is excluded.
        if any(part in _HASH_EXCLUDE_DIRS for part in child.relative_to(root).parts):
            continue
        yield child


def hash_tree(root: Path) -> str:
    """Return a deterministic ``sha256:<hex>`` over the file tree at *root*.

    The hash digests the sorted list of ``(posix-relpath, file-sha256)`` tuples,
    so it is stable across platforms and ignores file metadata.
    """

    if not root.exists():
        return "sha256:" + hashlib.sha256(b"").hexdigest()

    h = hashlib.sha256()
    for f in _iter_files(root):
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

    sha, _matched = _resolve_ref(url, ref)
    return sha


def resolve_ref(url: str, ref: str) -> tuple[str, str | None]:
    """Resolve *ref* and report what kind of upstream ref it matched.

    Returns ``(sha, matched_kind)`` where ``matched_kind`` is one of
    ``"tag"``, ``"branch"``, ``"sha"`` or ``None``. ``sha`` is always
    the underlying commit SHA (annotated tags are peeled).
    """

    if _looks_like_full_sha(ref):
        return ref.lower(), "sha"
    return _resolve_ref(url, ref)


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
