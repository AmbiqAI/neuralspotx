"""Dataclass models for ``nsx.lock`` documents."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .._errors import NSXLockError
from ._constants import LOCK_SCHEMA_VERSION
from ._kinds import LockKind


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
            "modules": {name: entry.to_yaml_dict() for name, entry in self.modules.items()},
        }

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> "NsxLock":
        if not isinstance(data, dict):
            raise ValueError("nsx.lock root must be a mapping")
        version = int(data.get("schema_version", LOCK_SCHEMA_VERSION))
        if version != LOCK_SCHEMA_VERSION:
            raise NSXLockError(
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
