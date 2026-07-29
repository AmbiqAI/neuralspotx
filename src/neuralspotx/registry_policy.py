"""Contributor policy checks for immutable stable-registry revisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Iterable

_FULL_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{40}$")
_VERSION_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:[A-Za-z0-9._-]+-)?v\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?$"
)


@dataclass(frozen=True, slots=True)
class FloatingRefAllowance:
    """One temporary exception for a known stable-registry floating ref."""

    project: str
    revision: str
    reason: str
    removal_condition: str


@dataclass(frozen=True, slots=True)
class RegistryRefUse:
    """One registry location that resolves a project at a revision."""

    project: str
    revision: str
    location: str


@dataclass(frozen=True, slots=True)
class StableRegistryRefReport:
    """Structured result of evaluating stable registry revisions."""

    approved_floating: tuple[RegistryRefUse, ...]
    unapproved_floating: tuple[RegistryRefUse, ...]
    unused_allowances: tuple[FloatingRefAllowance, ...]

    @property
    def is_valid(self) -> bool:
        return not self.unapproved_floating and not self.unused_allowances


class StableRegistryRefPolicyError(ValueError):
    """Raised when stable registry refs or their temporary allowances drift."""

    def __init__(self, report: StableRegistryRefReport) -> None:
        details = [
            f"{use.location}: {use.project}@{use.revision}"
            for use in report.unapproved_floating
        ]
        details.extend(
            f"unused allowance: {allowance.project}@{allowance.revision}"
            for allowance in report.unused_allowances
        )
        super().__init__(
            "Stable registry refs must use a version tag or full commit SHA; "
            + "; ".join(details)
        )
        self.report = report


TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST: Final[tuple[FloatingRefAllowance, ...]] = (
    FloatingRefAllowance(
        project="neuralspotx",
        revision="main",
        reason="Packaged board and tooling modules currently resolve from this release branch.",
        removal_condition="Replace packaged self-references with the released neuralspotx tag or SHA.",
    ),
    FloatingRefAllowance(
        project="nsx-ambiq-sdk",
        revision="main",
        reason="The unified SDK registry entries predate its first immutable release pin.",
        removal_condition="Remove when the registry moves to the released nsx-ambiq-sdk tag or SHA.",
    ),
)


def is_immutable_registry_revision(revision: str) -> bool:
    """Return whether *revision* is a full SHA or a version-shaped tag."""

    return bool(_FULL_SHA_RE.fullmatch(revision) or _VERSION_TAG_RE.fullmatch(revision))


def stable_registry_ref_report(
    registry: dict[str, Any],
    *,
    allowances: Iterable[FloatingRefAllowance] = TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST,
) -> StableRegistryRefReport:
    """Evaluate stable project/module/profile refs against exact exceptions."""

    allowance_tuple = tuple(allowances)
    allowance_keys = {(item.project, item.revision) for item in allowance_tuple}
    floating = tuple(
        use for use in _stable_registry_ref_uses(registry)
        if not is_immutable_registry_revision(use.revision)
    )
    approved = tuple(
        use for use in floating if (use.project, use.revision) in allowance_keys
    )
    unapproved = tuple(
        use for use in floating if (use.project, use.revision) not in allowance_keys
    )
    used_keys = {(use.project, use.revision) for use in floating}
    unused = tuple(
        allowance
        for allowance in allowance_tuple
        if (allowance.project, allowance.revision) not in used_keys
    )
    return StableRegistryRefReport(
        approved_floating=approved,
        unapproved_floating=unapproved,
        unused_allowances=unused,
    )


def validate_stable_registry_refs(
    registry: dict[str, Any],
    *,
    allowances: Iterable[FloatingRefAllowance] = TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST,
) -> StableRegistryRefReport:
    """Return a valid report or raise with every policy violation."""

    report = stable_registry_ref_report(registry, allowances=allowances)
    if not report.is_valid:
        raise StableRegistryRefPolicyError(report)
    return report


def _stable_registry_ref_uses(registry: dict[str, Any]) -> tuple[RegistryRefUse, ...]:
    uses: set[RegistryRefUse] = set()

    projects = registry.get("projects", {})
    if isinstance(projects, dict):
        for project, raw in projects.items():
            _add_ref_use(uses, project, raw, f"projects.{project}")

    modules = registry.get("modules", {})
    if isinstance(modules, dict):
        for module, raw in modules.items():
            if not isinstance(raw, dict):
                continue
            project = raw.get("project")
            _add_ref_use(uses, project, raw, f"modules.{module}")

    profiles = registry.get("starter_profiles", {})
    if isinstance(profiles, dict):
        for profile_name, profile in profiles.items():
            if not isinstance(profile, dict) or profile.get("channel", "stable") != "stable":
                continue
            for section in ("project_overrides", "module_overrides"):
                overrides = profile.get(section, {})
                if not isinstance(overrides, dict):
                    continue
                for name, raw in overrides.items():
                    project = name if section == "project_overrides" else (
                        raw.get("project") if isinstance(raw, dict) else None
                    )
                    _add_ref_use(
                        uses,
                        project,
                        raw,
                        f"starter_profiles.{profile_name}.{section}.{name}",
                    )

    return tuple(sorted(uses, key=lambda use: (use.project, use.revision, use.location)))


def _add_ref_use(
    uses: set[RegistryRefUse],
    project: object,
    raw: object,
    location: str,
) -> None:
    if not isinstance(project, str) or not isinstance(raw, dict):
        return
    revision = raw.get("revision")
    if isinstance(revision, str) and revision:
        uses.add(RegistryRefUse(project=project, revision=revision, location=location))
