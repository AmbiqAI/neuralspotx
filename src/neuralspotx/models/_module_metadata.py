"""Typed facade over a validated ``nsx-module.yaml`` mapping.

The parsed registry metadata is a deeply-nested ``dict`` that the
dependency-closure and policy code previously indexed by hand
(``meta["support"]["ambiqsuite"]``, ``meta["depends"]["required"]``, ...).
This facade exposes the *structural* fields the resolver depends on as typed
properties while keeping the open-ended discovery / semantic payload in
:attr:`raw`, so newly authored metadata keys keep flowing through unchanged.

It is only constructed *after* ``validate_nsx_module_metadata`` has run, so the
structural keys read below are guaranteed to be present and correctly typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModuleMetadata:
    """Typed view of a validated ``nsx-module.yaml`` mapping."""

    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> ModuleMetadata:
        return cls(raw=data)

    @property
    def name(self) -> str:
        return self.raw["module"]["name"]

    @property
    def module_type(self) -> str:
        return self.raw["module"]["type"]

    @property
    def version(self) -> str:
        return self.raw["module"]["version"]

    @property
    def supports_ambiqsuite(self) -> bool:
        return bool(self.raw["support"]["ambiqsuite"])

    @property
    def required_deps(self) -> list[str]:
        return self.raw["depends"]["required"]

    @property
    def optional_deps(self) -> list[str]:
        return self.raw["depends"]["optional"]

    @property
    def compatibility(self) -> dict[str, Any]:
        return self.raw["compatibility"]

    @property
    def required_sdk_provider(self) -> str | None:
        """The ``constraints.required_sdk_provider`` field, if authored.

        ``constraints`` is an optional, open-ended block, so this reads
        defensively rather than assuming the key is present.
        """

        constraints = self.raw.get("constraints")
        if not isinstance(constraints, dict):
            return None
        provider = constraints.get("required_sdk_provider")
        return provider if isinstance(provider, str) else None
