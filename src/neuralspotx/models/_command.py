"""CLI command graph hints + ``api.doctor`` report dataclasses."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

# ------------------------------------------------------------------
# CLI command descriptors
# ------------------------------------------------------------------


class CommandCategory(str, enum.Enum):
    """Category tag for CLI command graph hints."""

    ENTRYPOINT = "entrypoint"
    DISCOVERY = "discovery"
    APP_CREATION = "app-creation"
    DIAGNOSTICS = "diagnostics"
    BUILD = "build"
    DEPLOY = "deploy"
    MODULES = "modules"
    MAINTENANCE = "maintenance"


class CommandScope(str, enum.Enum):
    """Scope tag for CLI command graph hints."""

    GLOBAL = "global"
    APP = "app"
    ENVIRONMENT = "environment"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True)
class CommandHint:
    """Typed metadata hint for a CLI command in the command graph."""

    category: CommandCategory
    scope: CommandScope
    next_commands: tuple[str, ...] = ()
    alias_for: str | None = None

    def to_dict(self) -> dict[str, str | list[str]]:
        out: dict[str, str | list[str]] = {
            "category": self.category.value,
            "scope": self.scope.value,
            "next_commands": list(self.next_commands),
        }
        if self.alias_for is not None:
            out["alias_for"] = self.alias_for
        return out


@dataclass(frozen=True)
class DoctorCheck:
    """One environment / toolchain check produced by ``api.doctor()``.

    *required* discriminates checks that gate ``ok`` (e.g. ``cmake``)
    from informational ones (e.g. ATfE when ``ATFE_ROOT`` is set, or
    individual armclang components when the toolchain was detected).
    """

    label: str
    ok: bool
    required: bool = True
    detail: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "ok": self.ok,
            "required": self.required,
            "detail": self.detail,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class DoctorReport:
    """Aggregate result returned by ``api.doctor()``.

    ``ok`` is ``True`` iff every *required* check passed.
    ``checks`` preserves the order in which checks ran so embedders can
    render a deterministic table. ``notes`` carries free-form lines
    (e.g. "ATfE toolchain not detected — optional") for parity with the
    historic CLI output.
    """

    checks: tuple[DoctorCheck, ...]
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "notes": list(self.notes),
        }
