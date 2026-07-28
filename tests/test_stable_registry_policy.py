"""Stable registry refs are immutable except for exact temporary allowances."""

from __future__ import annotations

import pytest

from neuralspotx import load_registry
from neuralspotx.registry_policy import (
    TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST,
    FloatingRefAllowance,
    StableRegistryRefPolicyError,
    stable_registry_ref_report,
    validate_stable_registry_refs,
)


def test_packaged_registry_floating_refs_are_exactly_allowlisted() -> None:
    report = validate_stable_registry_refs(load_registry())

    assert {
        (use.project, use.revision) for use in report.approved_floating
    } == {
        ("neuralspotx", "main"),
        ("nsx-ambiq-sdk", "main"),
    }
    assert {
        (allowance.project, allowance.revision)
        for allowance in TEMPORARY_STABLE_FLOATING_REF_ALLOWLIST
    } == {
        ("neuralspotx", "main"),
        ("nsx-ambiq-sdk", "main"),
    }


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
    )

    report = stable_registry_ref_report(registry, allowances=(allowance,))

    assert report.unused_allowances == (allowance,)
    with pytest.raises(StableRegistryRefPolicyError):
        validate_stable_registry_refs(registry, allowances=(allowance,))
