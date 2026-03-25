"""Typed internal models for NSX registry, manifest, and app metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProjectEntry:
    """A project entry from the packaged registry, app overrides, or west manifest."""

    name: str
    url: str | None = None
    revision: str | None = None
    path: str | None = None
    local_path: str | None = None

    @classmethod
    def from_mapping(
        cls,
        name: str,
        data: dict[str, Any] | None,
        *,
        default_revision: str | None = None,
    ) -> ProjectEntry:
        if not isinstance(data, dict):
            return cls(name=name, revision=default_revision)
        revision = data.get("revision")
        if not isinstance(revision, str) or not revision:
            revision = default_revision
        url = data.get("url")
        path = data.get("path")
        local_path = data.get("local_path")
        return cls(
            name=name,
            url=url if isinstance(url, str) and url else None,
            revision=revision,
            path=path if isinstance(path, str) and path else None,
            local_path=local_path if isinstance(local_path, str) and local_path else None,
        )

    def to_mapping(self) -> dict[str, str]:
        out = {"name": self.name}
        if self.url:
            out["url"] = self.url
        if self.revision:
            out["revision"] = self.revision
        if self.path:
            out["path"] = self.path
        if self.local_path:
            out["local_path"] = self.local_path
        return out


@dataclass(frozen=True)
class ModuleEntry:
    """An app-local module registry entry."""

    name: str
    project: str
    revision: str
    metadata: str | None = None

    def to_mapping(self) -> dict[str, str]:
        out = {
            "project": self.project,
            "revision": self.revision,
        }
        if self.metadata:
            out["metadata"] = self.metadata
        return out
