"""Public registry snapshots must not let callers change shared packaged facts."""

from copy import deepcopy

import neuralspotx
from neuralspotx import api


def test_registry_nested_mutation_does_not_change_other_callers() -> None:
    registry = api.load_registry()
    expected = deepcopy(registry)
    registry["projects"]["neuralspotx"]["url"] = "caller-only"
    registry["starter_profiles"]["apollo510_evb_minimal"]["modules"].clear()
    registry["caller-only"] = {"values": [1]}

    assert api.load_registry() == expected
    assert api.starter_profile("apollo510_evb") == expected["starter_profiles"][
        "apollo510_evb_minimal"
    ]
    assert api.registry_module_project("nsx-core") == expected["modules"]["nsx-core"][
        "project"
    ]


def test_profile_nested_mutation_does_not_change_registry_or_profiles() -> None:
    expected = api.load_registry()
    profile = api.starter_profile("apollo510_evb")
    assert profile is not None
    profile["modules"].clear()
    profile["caller-only"] = {"values": [1]}

    assert api.starter_profile("apollo510_evb") == expected["starter_profiles"][
        "apollo510_evb_minimal"
    ]
    assert api.load_registry() == expected


def test_missing_registry_entries_remain_none() -> None:
    assert api.starter_profile("not-a-packaged-board") is None
    assert api.registry_module_project("not-a-packaged-module") is None


def test_facade_exports_exclude_implementation_module_but_keep_compatibility() -> None:
    assert "operations" not in api.__all__
    assert "operations" not in neuralspotx.__all__
    assert "PathLike" in api.__all__
    assert api.operations is neuralspotx.operations
    for name in api.__all__:
        assert hasattr(api, name)
