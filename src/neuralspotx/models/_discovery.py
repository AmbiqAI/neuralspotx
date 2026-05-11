"""Module discovery records returned by list/describe/search APIs."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

# ------------------------------------------------------------------
# Module discovery records
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SearchMatch:
    """A single field match from module search scoring."""

    field: str
    term: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "term": self.term, "value": self.value}


_DISCOVERY_RICH_FIELDS = ("module", "support", "build", "depends", "compatibility")
_DISCOVERY_SEMANTIC_FIELDS = (
    "summary",
    "capabilities",
    "use_cases",
    "anti_use_cases",
    "agent_keywords",
    "example_refs",
    "composition_hints",
    "provides",
    "constraints",
    "integrations",
)


@dataclass(frozen=True)
class DiscoveryRecord:
    """Typed module discovery record returned by list/describe/search APIs."""

    # Core fields (always present)
    name: str
    project: str
    revision: str
    metadata: str | None
    enabled: bool

    # Metadata availability
    metadata_available: bool = False
    metadata_error: str | None = None

    # Rich metadata (only when metadata_available is True)
    module: dict[str, Any] | None = None
    support: dict[str, Any] | None = None
    build: dict[str, Any] | None = None
    depends: dict[str, Any] | None = None
    compatibility: dict[str, Any] | None = None

    # Optional semantic metadata
    summary: str | None = None
    capabilities: list[str] | None = None
    use_cases: list[str] | None = None
    anti_use_cases: list[str] | None = None
    agent_keywords: list[str] | None = None
    example_refs: list[Any] | None = None
    composition_hints: dict[str, Any] | None = None
    provides: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict matching the legacy discovery record format."""
        out: dict[str, Any] = {
            "name": self.name,
            "project": self.project,
            "revision": self.revision,
            "metadata": self.metadata,
            "enabled": self.enabled,
        }
        if self.metadata_error is not None:
            out["metadata_available"] = False
            out["metadata_error"] = self.metadata_error
            return out
        if not self.metadata_available:
            return out
        out["metadata_available"] = True
        for field in _DISCOVERY_RICH_FIELDS:
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        for field in _DISCOVERY_SEMANTIC_FIELDS:
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        return out


@dataclass(frozen=True)
class SearchResult(DiscoveryRecord):
    """A discovery record augmented with search scoring."""

    score: int = 0
    matches: tuple[SearchMatch, ...] = ()
    compatible: bool | None = None

    @classmethod
    def from_record(
        cls,
        record: DiscoveryRecord,
        *,
        score: int,
        matches: tuple[SearchMatch, ...],
        compatible: bool | None,
    ) -> SearchResult:
        base = {f.name: getattr(record, f.name) for f in dataclasses.fields(DiscoveryRecord)}
        return cls(**base, score=score, matches=matches, compatible=compatible)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out["score"] = self.score
        out["matches"] = [m.to_dict() for m in self.matches]
        out["compatible"] = self.compatible
        return out
