"""Contributor policy checks for immutable stable-registry revisions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Iterable

_FULL_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{40}$")
_VERSION_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:[A-Za-z0-9._-]+-)?v\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?$"
)

# Project records that are intentionally kept even though nothing in the
# packaged registry currently points a module or starter-profile override at
# them. Empty today: when a module's source is absorbed into another project
# (e.g. consolidated into `nsx-ambiq-sdk`), the matching `projects.<name>`
# record must be deleted in the *same* change (see PR #113 / commit
# c50d7e8, "chore(registry): drop dead module entries absorbed into unified
# SDK"). If a future project record is ever kept on purpose as a documented
# backward-compatible override anchor (e.g. so
# `module_registry.modules.<m>.project: <name>` keeps working without an
# app needing to also supply a `module_registry.projects.<name>` stanza),
# add its name here with a comment explaining the contract instead of
# silently leaving it orphaned.
RESERVED_REGISTRY_PROJECT_NAMES: Final[frozenset[str]] = frozenset()


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


@dataclass(frozen=True, slots=True)
class OrphanedProjectReport:
    """Structured result of checking `projects` for unreferenced records."""

    orphaned: tuple[str, ...]
    reserved: tuple[str, ...]
    stale_reserved: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.orphaned and not self.stale_reserved


def _referenced_project_names(registry: dict[str, Any]) -> set[str]:
    """Every project name reachable from a module, family, or profile override.

    A project is "reachable" when at least one of the following points at it
    by name:

    * a `modules.<module>.project` entry (the default resolution path),
    * a `soc_families.<family>.project` entry (the SDK-provider baseline a
      family resolves to, even before it has any `board_profiles` entry to
      derive a starter profile from — see `metadata._derive_starter_profiles`,
      which only emits `project_overrides` for families with a registered
      board), or
    * a `starter_profiles.<profile>.project_overrides` / `.module_overrides`
      entry (the derived-profile resolution path).

    This intentionally mirrors runtime resolution (`_registry_project_entry`
    is only ever called with a project name sourced from one of these
    places) rather than doing a network reachability check; see
    `scripts/audit_registry_project_urls.py` for the separate, network-based
    URL-liveness audit.
    """

    referenced: set[str] = set()

    modules = registry.get("modules", {})
    if isinstance(modules, dict):
        for entry in modules.values():
            if isinstance(entry, dict) and isinstance(entry.get("project"), str):
                referenced.add(entry["project"])

    families = registry.get("soc_families", {})
    if isinstance(families, dict):
        for family in families.values():
            if isinstance(family, dict) and isinstance(family.get("project"), str):
                referenced.add(family["project"])

    profiles = registry.get("starter_profiles", {})
    if isinstance(profiles, dict):
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            project_overrides = profile.get("project_overrides", {})
            if isinstance(project_overrides, dict):
                referenced.update(name for name in project_overrides if isinstance(name, str))
            module_overrides = profile.get("module_overrides", {})
            if isinstance(module_overrides, dict):
                for override in module_overrides.values():
                    if isinstance(override, dict) and isinstance(override.get("project"), str):
                        referenced.add(override["project"])

    return referenced


def orphaned_registry_project_report(
    registry: dict[str, Any],
    *,
    reserved: Iterable[str] = RESERVED_REGISTRY_PROJECT_NAMES,
) -> OrphanedProjectReport:
    """Return every packaged `projects` entry no module/profile resolves to.

    Reports project records that would silently rot the way the pre-cleanup
    `nsx-soc-hal` / `nsx-cmsis-core` / `nsx-cmsis-startup` / `nsx-core` /
    `nsx-perf` / `nsx-uart` / `nsx-i2c` / `nsx-spi` / `nsx-audio` / `nsx-usb`
    single-module-repo records did after their modules were repointed at the
    unified `nsx-ambiq-sdk` monorepo (PR #113) without removing the now-dead
    per-module project entries. Names in *reserved* are exempt (see
    `RESERVED_REGISTRY_PROJECT_NAMES`); a reserved name no longer present in
    `projects` at all is reported in `stale_reserved` (mirrors
    `StableRegistryRefReport.unused_allowances` for the immutable-ref check
    above: a reservation that stops applying must be removed, not left
    behind as dead configuration).
    """

    reserved_set = frozenset(reserved)
    projects = registry.get("projects", {})
    project_names = set(projects) if isinstance(projects, dict) else set()
    referenced = _referenced_project_names(registry)
    orphaned = tuple(sorted(project_names - referenced - reserved_set))
    used_reserved = tuple(sorted(reserved_set & project_names))
    stale_reserved = tuple(sorted(reserved_set - project_names))
    return OrphanedProjectReport(
        orphaned=orphaned, reserved=used_reserved, stale_reserved=stale_reserved
    )
