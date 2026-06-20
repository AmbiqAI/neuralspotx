"""Profile-seeded resolution for lean manifests.

A lean ``nsx.yml`` omits the resolved module closure and registry
overrides; ``expand_profile_seeds`` rebuilds them in-memory from the
app's starter profile so the resolver sees a config that is
byte-compatible with a freshly-scaffolded (inlined) app.
"""

from __future__ import annotations

import pytest

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
