"""Cache snapshot dataclasses returned by ``api.cache_info`` / ``api.clean_cache``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    """A single entry in the NSX module artifact cache."""

    digest: str
    path: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"digest": self.digest, "path": self.path, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class CacheInfo:
    """Snapshot of the NSX module artifact cache."""

    root: str
    disabled: bool
    entries: tuple[CacheEntry, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def total_size_bytes(self) -> int:
        return sum(e.size_bytes for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "disabled": self.disabled,
            "entry_count": self.entry_count,
            "entries": [e.to_dict() for e in self.entries],
            "total_size_bytes": self.total_size_bytes,
        }


@dataclass(frozen=True)
class CacheCleanResult:
    """Outcome of an :func:`api.clean_cache` invocation."""

    root: str
    removed_count: int
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "removed_count": self.removed_count,
            "dry_run": self.dry_run,
        }
