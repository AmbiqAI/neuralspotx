"""Profile-seeded resolution for lean manifests.

A lean ``nsx.yml`` omits the resolved module closure and registry
overrides; ``expand_profile_seeds`` rebuilds them in-memory from the
app's starter profile so the resolver sees a config that is
byte-compatible with a freshly-scaffolded (inlined) app.
"""

from __future__ import annotations

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.module_registry import (
    _generate_nsx_config,
    _module_names_from_nsx,
    expand_profile_seeds,
)
from neuralspotx.project_config import _load_registry

BOARD = "apollo510_evb"
SOC = "apollo510"


def _inlined_cfg() -> dict:
    return _generate_nsx_config(
        "demo",
        BOARD,
        SOC,
        _load_registry(),
        default_toolchain="arm-none-eabi-gcc",
        nsx_version="1.2.3",
        nsx_major=1,
    )


def test_lean_manifest_expands_to_inlined_closure() -> None:
    registry = _load_registry()
    inlined = _inlined_cfg()

    lean = {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "profile": f"{BOARD}_minimal",
    }
    expanded = expand_profile_seeds(lean, registry)

    assert expanded["modules"] == inlined["modules"]
    assert expanded["module_registry"] == inlined["module_registry"]
    assert _module_names_from_nsx(expanded) == _module_names_from_nsx(inlined)


def test_inlined_manifest_passes_through_unchanged() -> None:
    registry = _load_registry()
    inlined = _inlined_cfg()

    expanded = expand_profile_seeds(inlined, registry)

    # Already has a closure -> returned as-is (same object, no rebuild).
    assert expanded is inlined


def test_explicit_empty_modules_passes_through_unchanged() -> None:
    # `--no-bootstrap` writes an intentional `modules: []`; the key is
    # present so it must NOT be re-seeded from the profile.
    registry = _load_registry()
    cfg = {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "profile": f"{BOARD}_minimal",
        "modules": [],
    }
    expanded = expand_profile_seeds(cfg, registry)

    assert expanded is cfg
    assert expanded["modules"] == []


def test_authored_module_registry_is_preserved() -> None:
    registry = _load_registry()
    lean = {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "profile": f"{BOARD}_minimal",
        "module_registry": {"projects": {"custom": {"url": "x"}}, "modules": {}},
    }
    expanded = expand_profile_seeds(lean, registry)

    assert expanded["modules"]  # closure still seeded
    assert expanded["module_registry"] == {"projects": {"custom": {"url": "x"}}, "modules": {}}


def test_missing_board_is_a_no_op() -> None:
    registry = _load_registry()
    lean = {"schema_version": 1, "project": {"name": "demo"}}

    expanded = expand_profile_seeds(lean, registry)

    assert "modules" not in expanded


@pytest.mark.parametrize(
    "board,soc", [("apollo510_evb", "apollo510"), ("apollo4p_evb", "apollo4p")]
)
def test_multiple_boards_seed_distinct_closures(board: str, soc: str) -> None:
    registry = _load_registry()
    lean = {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": board, "soc": soc},
        "profile": f"{board}_minimal",
    }
    expanded = expand_profile_seeds(lean, registry)
    names = _module_names_from_nsx(expanded)
    assert names
    assert any(n.startswith("nsx-board-") for n in names)


# --- additive `requires` --------------------------------------------------


def _lean_with_requires(requires: object) -> dict:
    return {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "profile": f"{BOARD}_minimal",
        "requires": requires,
    }


def test_requires_appends_extras_after_profile_seed() -> None:
    registry = _load_registry()
    base = _module_names_from_nsx(expand_profile_seeds(_lean_with_requires([]), registry))

    expanded = expand_profile_seeds(_lean_with_requires(["nsx-usb"]), registry)
    names = _module_names_from_nsx(expanded)

    # Additive: every base module is retained and the extra is appended last.
    assert names[: len(base)] == base
    assert names[-1] == "nsx-usb"


def test_requires_resolves_family_catalog_module_metadata() -> None:
    # nsx-timer lives in the board family's ``sdk_modules`` catalog, not the
    # top-level registry ``modules`` map; it must still resolve with its
    # metadata path seeded into ``module_registry``.
    registry = _load_registry()
    expanded = expand_profile_seeds(_lean_with_requires(["nsx-timer"]), registry)

    assert "nsx-timer" in _module_names_from_nsx(expanded)
    timer = expanded["module_registry"]["modules"]["nsx-timer"]
    assert timer["metadata"] == "modules/nsx-timer/nsx-module.yaml"
    assert timer["project"]


def test_requires_duplicate_of_profile_module_is_a_no_op() -> None:
    registry = _load_registry()
    base = _module_names_from_nsx(expand_profile_seeds(_lean_with_requires([]), registry))
    profile_module = base[0]

    expanded = expand_profile_seeds(_lean_with_requires([profile_module]), registry)
    names = _module_names_from_nsx(expanded)

    # Already seeded by the profile -> not duplicated.
    assert names == base
    assert names.count(profile_module) == 1


def test_requires_dedupes_and_preserves_first_seen_order() -> None:
    registry = _load_registry()
    expanded = expand_profile_seeds(
        _lean_with_requires(["nsx-usb", "nsx-timer", "nsx-usb"]), registry
    )
    names = _module_names_from_nsx(expanded)

    assert names.count("nsx-usb") == 1
    assert names.index("nsx-usb") < names.index("nsx-timer")


def test_requires_mapping_entry_pins_explicit_project() -> None:
    registry = _load_registry()
    expanded = expand_profile_seeds(
        _lean_with_requires([{"name": "nsx-usb", "project": "custom-proj", "revision": "v9"}]),
        registry,
    )
    record = next(m for m in expanded["modules"] if m["name"] == "nsx-usb")

    assert record["project"] == "custom-proj"
    assert record["revision"] == "v9"


def test_requires_unknown_module_raises() -> None:
    registry = _load_registry()
    with pytest.raises(NSXConfigError, match="not in the board's module catalog"):
        expand_profile_seeds(_lean_with_requires(["nsx-does-not-exist"]), registry)


def test_requires_with_inlined_modules_is_mutually_exclusive() -> None:
    registry = _load_registry()
    inlined = _inlined_cfg()
    inlined["requires"] = ["nsx-usb"]

    with pytest.raises(NSXConfigError, match="mutually exclusive"):
        expand_profile_seeds(inlined, registry)


def test_requires_must_be_a_list() -> None:
    registry = _load_registry()
    with pytest.raises(NSXConfigError, match="'requires' must be a list"):
        expand_profile_seeds(_lean_with_requires({"nsx-usb": True}), registry)
