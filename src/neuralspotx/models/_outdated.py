"""``api.outdated_app`` report dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ------------------------------------------------------------------
# Outdated report (api.outdated_app)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class OutdatedModule:
    """One git-hosted module's drift between locked commit and upstream tip.

    *status* is a ``str``-mixed enum value (``OutdatedStatus``) so plain
    string comparisons against ``"up-to-date"`` / ``"outdated"`` keep
    working for embedders that don't import the enum.
    """

    name: str
    constraint: str
    locked: str
    upstream: str
    status: str
    url: str = ""

    @property
    def is_outdated(self) -> bool:
        return self.status == "outdated"

    def to_dict(self) -> dict[str, str]:
        return {
            "module": self.name,
            "constraint": self.constraint,
            "locked": self.locked,
            "upstream": self.upstream,
            "status": str(self.status),
            "url": self.url,
        }


@dataclass(frozen=True)
class OutdatedSkip:
    """A module that ``api.outdated_app`` could not check, with a reason."""

    name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"module": self.name, "reason": self.reason}


@dataclass(frozen=True)
class OutdatedReport:
    """Aggregate result returned by ``api.outdated_app()``.

    ``checked`` preserves the order in which modules were inspected so
    embedders can render a deterministic table; ``skipped`` records
    modules that could not be resolved (no URL, ``git ls-remote``
    failure, etc.). The ``outdated`` property is a convenience filter
    that mirrors what the historic CLI returned as an integer count.
    """

    checked: tuple[OutdatedModule, ...]
    skipped: tuple[OutdatedSkip, ...] = ()

    @property
    def outdated(self) -> tuple[OutdatedModule, ...]:
        return tuple(m for m in self.checked if m.is_outdated)

    @property
    def outdated_count(self) -> int:
        return len(self.outdated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": [m.to_dict() for m in self.checked],
            "skipped": [s.to_dict() for s in self.skipped],
            "outdated_count": self.outdated_count,
        }
