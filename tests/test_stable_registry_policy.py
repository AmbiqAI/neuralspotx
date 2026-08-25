"""Stable registry refs are immutable except for exact temporary allowances."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from neuralspotx import load_registry
from neuralspotx.registry_policy import (
    RESERVED_REGISTRY_PROJECT_NAMES,
    TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST,
    FloatingRefAllowance,
    StableRegistryRefPolicyError,
    orphaned_registry_project_report,
    stable_registry_ref_report,
    validate_stable_registry_refs,
)


def test_packaged_registry_floating_refs_are_exactly_allowlisted() -> None:
    report = validate_stable_registry_refs(load_registry())

    expected = {
        ("neuralspotx", "main"),
        # Temporary atomiq110 branch pins — collapse once the atomiq110
        # support PRs merge and release tags exist.
        ("helia-rt", "fix/atomiq110-compat"),
        ("nsx-ambiq-sdk", "feat/nsx-power-atomiq110"),
    }
    assert {(use.project, use.revision) for use in report.approved_floating} == expected
    assert {
        (allowance.project, allowance.revision)
        for allowance in TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST
    } == expected
    # Only the packaged self-reference may be permanent; every branch pin
    # must carry an expiry so it cannot silently outlive its upstream PR.
    assert {
        (allowance.project, allowance.revision)
        for allowance in TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST
        if allowance.is_permanent
    } == {("neuralspotx", "main")}


def test_temporary_allowances_have_not_expired() -> None:
    """A branch pin past its ``expires_on`` date must be re-pinned, not kept.

    Fails with the exact ``project@revision`` and the recorded
    ``removal_condition`` so the fix is actionable from the failure alone.
    """

    report = stable_registry_ref_report(load_registry())

    expired = [
        f"{allowance.project}@{allowance.revision} expired on "
        f"{allowance.expires_on}: {allowance.removal_condition}"
        for allowance in report.expired_allowances
    ]
    assert not expired, (
        "Temporary floating-ref allowances have expired; re-pin the registry and "
        "drop the allowance:\n  " + "\n  ".join(expired)
    )


def test_packaged_registry_release_projects_are_immutable() -> None:
    registry = load_registry()

    assert registry["projects"]["nsx-ambiq-sdk"]["revision"] == "v5.2.24"
    assert registry["projects"]["nsx-pmu-armv8m"]["revision"] == "v0.2.0"
    assert (
        registry["projects"]["nsx-ethos-u-driver"]["revision"]
        == "nsx-ethos-u-driver-v0.1.2"
    )
    assert registry["projects"]["arm-cmsis-nn"]["revision"] == "v0.1.0"
    assert registry["projects"]["nsx-tflite-micro"]["revision"] == "v0.1.0"
    assert registry["projects"]["ns-cmsis-nn"]["revision"] == "v7.29.2"
    assert registry["projects"]["nsx-nanopb"]["revision"] == "v0.1.1"
    assert registry["projects"]["helia-dsp"]["revision"] == "v1.0.0"
    assert registry["projects"]["nsx-tileio"]["revision"] == "v0.1.0"
    assert registry["projects"]["nsx-physiokit"]["revision"] == "v0.1.0"
    assert registry["projects"]["nsx-sensors"]["revision"] == "v0.3.0"
    assert registry["modules"]["nsx-pmu-armv8m"]["revision"] == "v0.2.0"
    assert registry["modules"]["arm-cmsis-nn"]["revision"] == "v0.1.0"
    assert registry["modules"]["nsx-tflite-micro"]["revision"] == "v0.1.0"
    assert registry["modules"]["nsx-cmsis-nn"]["revision"] == "v7.29.2"
    assert registry["modules"]["nsx-nanopb"]["revision"] == "v0.1.1"
    assert registry["modules"]["helia-dsp"]["revision"] == "v1.0.0"
    assert registry["modules"]["nsx-physiokit"]["revision"] == "v0.1.0"
    assert registry["modules"]["nsx-sensors"]["revision"] == "v0.3.0"
    assert {
        entry["revision"]
        for entry in registry["modules"].values()
        if entry["project"] == "nsx-tileio"
    } == {"v0.1.0"}
    # Every nsx-ambiq-sdk ref is either the release tag or an explicitly
    # allowlisted floating ref. Derived from the allowlist (rather than
    # spelling the branch here) so this test never *requires* a branch pin
    # to be present: collapsing a temporary pin back to the tag must not
    # break it.
    sdk_release_tag = "v5.2.24"
    allowed_sdk_refs = {sdk_release_tag} | {
        allowance.revision
        for allowance in TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST
        if allowance.project == "nsx-ambiq-sdk"
    }
    sdk_module_refs = {
        entry["revision"]
        for entry in registry["modules"].values()
        if entry["project"] == "nsx-ambiq-sdk"
    }
    assert sdk_release_tag in sdk_module_refs
    assert sdk_module_refs <= allowed_sdk_refs
    sdk_profile_refs = {
        profile["project_overrides"]["nsx-ambiq-sdk"]["revision"]
        for profile in registry["starter_profiles"].values()
    }
    assert sdk_release_tag in sdk_profile_refs
    assert sdk_profile_refs <= allowed_sdk_refs


def test_packaged_registry_has_no_orphaned_projects() -> None:
    """Every packaged `projects` record must be reachable from the graph.

    Guards against the exact regression this test was added to fix: modules
    absorbed into `nsx-ambiq-sdk` (PR #113) repointed their
    `modules.<name>.project` field but left the old single-module-repo
    `projects.<name>` records (`nsx-soc-hal`, `nsx-cmsis-core`,
    `nsx-cmsis-startup`, `nsx-core`, `nsx-perf`, `nsx-uart`, `nsx-i2c`,
    `nsx-spi`, `nsx-audio`, `nsx-usb`) behind, dangling and unreferenced. A
    future SDK-consolidation change that forgets the matching project-record
    cleanup fails here instead of shipping silently.
    """

    report = orphaned_registry_project_report(load_registry())

    assert report.orphaned == ()
    assert report.stale_reserved == ()
    assert report.is_valid


def test_orphaned_registry_project_report_detects_dangling_records() -> None:
    """Synthetic-registry unit test for the underlying policy function.

    Exercises every way a project name may be considered "referenced" (a
    module's `project`, a SoC family's `project` baseline — reachable even
    before that family has any `board_profiles` entry to derive a starter
    profile from, a profile's `project_overrides` key, and a profile's
    `module_overrides.<module>.project`) plus the reserved-name escape hatch
    and its `stale_reserved` counterpart, without depending on the shape of
    the shipped registry.
    """

    registry = {
        "projects": {
            "used-by-module": {"revision": "v1"},
            "used-by-family": {"revision": "v1"},
            "used-by-profile-override": {"revision": "v1"},
            "used-by-module-override": {"revision": "v1"},
            "dangling": {"revision": "v1"},
            "kept-on-purpose": {"revision": "v1"},
        },
        "modules": {
            "some-module": {"project": "used-by-module", "revision": "v1"},
        },
        "soc_families": {
            # No matching `board_profiles` entry below, so this family
            # contributes no `starter_profiles` project_override; only the
            # direct `soc_families.*.project` reachability path covers it.
            "boardless_family": {"project": "used-by-family", "revision": "v1"},
        },
        "starter_profiles": {
            "board_minimal": {
                "project_overrides": {"used-by-profile-override": {"revision": "v1"}},
                "module_overrides": {
                    "other-module": {
                        "project": "used-by-module-override",
                        "revision": "v1",
                    }
                },
            }
        },
    }

    report = orphaned_registry_project_report(registry)
    assert report.orphaned == ("dangling", "kept-on-purpose")
    assert report.reserved == ()
    assert report.stale_reserved == ()
    assert not report.is_valid

    report = orphaned_registry_project_report(registry, reserved={"kept-on-purpose"})
    assert report.orphaned == ("dangling",)
    assert report.reserved == ("kept-on-purpose",)
    assert report.stale_reserved == ()
    assert not report.is_valid


def test_orphaned_registry_project_report_flags_stale_reservations() -> None:
    """A reserved name that no longer exists in `projects` must be reported.

    Mirrors `test_stale_allowance_must_be_removed_after_immutable_transition`
    for the immutable-ref policy: once nothing needs a reservation anymore
    (the project record itself was deleted), the reservation is dead
    configuration and must be removed, not left dangling.
    """

    registry = {
        "projects": {"still-here": {"revision": "v1"}},
        "modules": {"m": {"project": "still-here", "revision": "v1"}},
    }

    report = orphaned_registry_project_report(registry, reserved={"long-gone"})
    assert report.orphaned == ()
    assert report.reserved == ()
    assert report.stale_reserved == ("long-gone",)
    assert not report.is_valid


def test_reserved_registry_project_names_is_empty_today() -> None:
    """No project is currently kept as a documented override-only anchor.

    If this ever needs to change, add the name to
    `RESERVED_REGISTRY_PROJECT_NAMES` together with a comment explaining the
    backward-compatible override contract it exists for — don't just widen
    this assertion.
    """

    assert RESERVED_REGISTRY_PROJECT_NAMES == frozenset()


def test_new_floating_module_ref_is_reported_without_broad_exception() -> None:
    registry = {
        "projects": {
            "stable-project": {"revision": "v1.2.3"},
            "new-project": {"revision": "v2.0.0"},
        },
        "modules": {
            "new-module": {
                "project": "new-project",
                "revision": "customer-bringup",
            }
        },
        "starter_profiles": {},
    }

    report = stable_registry_ref_report(registry, allowances=())

    assert [
        (use.project, use.revision, use.location)
        for use in report.unapproved_floating
    ] == [
        ("new-project", "customer-bringup", "modules.new-module"),
    ]
    with pytest.raises(StableRegistryRefPolicyError):
        validate_stable_registry_refs(registry, allowances=())


def test_allowance_is_exact_to_project_and_revision() -> None:
    registry = {
        "projects": {"nsx-ambiq-sdk": {"revision": "release-candidate"}},
        "modules": {},
        "starter_profiles": {},
    }

    report = stable_registry_ref_report(
        registry,
        allowances=TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST,
    )

    assert [(use.project, use.revision) for use in report.unapproved_floating] == [
        ("nsx-ambiq-sdk", "release-candidate")
    ]


def test_stale_allowance_must_be_removed_after_immutable_transition() -> None:
    registry = {
        "projects": {"sdk": {"revision": "v5.2.23"}},
        "modules": {},
        "starter_profiles": {},
    }
    allowance = FloatingRefAllowance(
        project="sdk",
        revision="main",
        reason="temporary",
        removal_condition="tag release",
        expires_on=date(2099, 1, 1),
    )

    report = stable_registry_ref_report(registry, allowances=(allowance,))

    assert report.unused_allowances == (allowance,)
    with pytest.raises(StableRegistryRefPolicyError):
        validate_stable_registry_refs(registry, allowances=(allowance,))


def test_expired_allowance_is_reported_with_removal_condition() -> None:
    """An allowance past ``expires_on`` is a policy violation naming its fix.

    Uses an injected *today* so the assertion is deterministic; the shipped
    allowlist is checked against the real clock by
    ``test_temporary_allowances_have_not_expired``.
    """

    registry = {
        "projects": {"sdk": {"revision": "feat/bringup"}},
        "modules": {},
        "starter_profiles": {},
    }
    expiry = date(2026, 10, 15)
    temporary = FloatingRefAllowance(
        project="sdk",
        revision="feat/bringup",
        reason="bring-up branch",
        removal_condition="Re-pin to the next sdk release tag.",
        expires_on=expiry,
    )
    permanent = FloatingRefAllowance(
        project="self",
        revision="main",
        reason="packaged self-reference",
        removal_condition="never",
        expires_on=None,
    )
    registry["projects"]["self"] = {"revision": "main"}

    # On and before the expiry date the allowance still applies.
    on_time = stable_registry_ref_report(
        registry, allowances=(temporary, permanent), today=expiry
    )
    assert on_time.expired_allowances == ()
    assert on_time.is_valid

    late = stable_registry_ref_report(
        registry,
        allowances=(temporary, permanent),
        today=expiry + timedelta(days=1),
    )
    assert late.expired_allowances == (temporary,)
    assert not late.is_valid
    assert permanent.is_permanent and not permanent.is_expired(date.max)

    with pytest.raises(StableRegistryRefPolicyError) as excinfo:
        validate_stable_registry_refs(
            registry,
            allowances=(temporary, permanent),
            today=expiry + timedelta(days=1),
        )
    message = str(excinfo.value)
    assert "sdk@feat/bringup" in message
    assert "Re-pin to the next sdk release tag." in message
    assert "2026-10-15" in message
