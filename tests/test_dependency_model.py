"""Schema v2 unified dependency model surface.

Schema v2 collapses the old ``requires:`` / authoritative-``modules:`` split
into a single ``modules:`` list mirroring cargo / uv / npm:

  * each entry is ``name`` + optional ``source`` (path / vendored / git) +
    optional ``boards`` filter;
  * bare-string entries (``- nsx-timer``) are shorthand for ``{name: ...}``;
  * the board profile is the implicit baseline, layered under ``modules:``;
  * ``baseline: none`` opts out, making ``modules:`` the authoritative closure.

These tests pin that surface: shorthand parsing, source round-trips, the
``boards`` filter + subset validation, ``baseline: none`` authoritative
closure, and the v2 validation errors (multi-source, ``rev`` without ``git``,
``boards`` not a declared target, empty bare string, removed ``requires:``).
"""

from __future__ import annotations

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.models import AppModule, NsxProject
from neuralspotx.module_registry import expand_profile_seeds
from neuralspotx.project_config import _load_registry

BOARD = "apollo510_evb"
SOC = "apollo510"


def _base_cfg(**overrides: object) -> dict:
    cfg: dict = {
        "schema_version": 2,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "toolchain": "arm-none-eabi-gcc",
        "modules": [],
    }
    cfg.update(overrides)
    return cfg


# --- bare-string shorthand -------------------------------------------------


def test_bare_string_entry_is_shorthand_for_name_mapping() -> None:
    project = NsxProject.from_mapping(_base_cfg(modules=["nsx-timer"]))

    assert project.modules == (AppModule(name="nsx-timer"),)
    only = project.modules[0]
    assert only.source_kind == "registry"
    assert only.boards == ()
    assert only.applies_to(BOARD) is True


def test_bare_string_and_mapping_entries_coexist() -> None:
    project = NsxProject.from_mapping(
        _base_cfg(modules=["nsx-timer", {"name": "nsx-usb", "project": "custom"}])
    )

    names = [m.name for m in project.modules]
    assert names == ["nsx-timer", "nsx-usb"]
    assert project.modules[1].project == "custom"


def test_empty_bare_string_entry_is_rejected() -> None:
    with pytest.raises(NSXConfigError) as excinfo:
        NsxProject.from_mapping(_base_cfg(modules=[""]))

    assert excinfo.value.field == "modules[0]"


# --- source round-trips ----------------------------------------------------


def test_path_source_round_trips_through_loader() -> None:
    cfg = _base_cfg(
        modules=[{"name": "my-driver", "source": {"path": "../my-driver"}}]
    )
    project = NsxProject.from_mapping(cfg)
    module = project.modules[0]

    assert module.source_kind == "path"
    assert module.is_local is True
    assert module.source.path == "../my-driver"

    reloaded = NsxProject.from_mapping(project.to_mapping())
    assert reloaded.modules[0].source.path == "../my-driver"
    assert reloaded.modules[0].source_kind == "path"


def test_vendored_source_round_trips_through_loader() -> None:
    cfg = _base_cfg(modules=[{"name": "aot-model", "source": {"vendored": True}}])
    project = NsxProject.from_mapping(cfg)
    module = project.modules[0]

    assert module.source_kind == "vendored"
    assert module.is_vendored is True
    assert module.is_opaque is True

    reloaded = NsxProject.from_mapping(project.to_mapping())
    assert reloaded.modules[0].is_vendored is True
    assert reloaded.modules[0].source_kind == "vendored"


# --- boards filter ---------------------------------------------------------


def test_boards_filter_scopes_dependency_to_listed_targets() -> None:
    cfg = _base_cfg(
        targets={"default": BOARD, "supported": [BOARD, "apollo510b_evb"]},
        modules=[{"name": "nsx-pdm", "boards": [BOARD]}],
    )
    project = NsxProject.from_mapping(cfg)
    module = project.modules[0]

    assert module.boards == (BOARD,)
    assert module.applies_to(BOARD) is True
    assert module.applies_to("apollo510b_evb") is False


def test_boards_filter_must_be_a_subset_of_supported_targets() -> None:
    cfg = _base_cfg(
        targets={"default": BOARD, "supported": [BOARD]},
        modules=[{"name": "nsx-pdm", "boards": ["not-a-real-board"]}],
    )
    with pytest.raises(NSXConfigError) as excinfo:
        NsxProject.from_mapping(cfg)

    assert excinfo.value.field == "modules[0].boards"


# --- baseline: none --------------------------------------------------------


def test_baseline_none_makes_modules_authoritative_closure() -> None:
    # With `baseline: none` the board profile is NOT seeded, so the closure is
    # exactly the listed `modules:`. A vendored (opaque) entry resolves without
    # any registry catalog, isolating the authoritative-closure behavior.
    registry = _load_registry()
    cfg = {
        "schema_version": 2,
        "project": {"name": "demo"},
        "target": {"board": BOARD, "soc": SOC},
        "profile": f"{BOARD}_minimal",
        "baseline": "none",
        "modules": [{"name": "aot-model", "source": {"vendored": True}}],
    }
    expanded = expand_profile_seeds(cfg, registry)

    names = [m["name"] for m in expanded["modules"]]
    assert names == ["aot-model"]


def test_default_baseline_layers_profile_under_modules() -> None:
    registry = _load_registry()
    seeded = expand_profile_seeds(
        {
            "schema_version": 2,
            "project": {"name": "demo"},
            "target": {"board": BOARD, "soc": SOC},
            "profile": f"{BOARD}_minimal",
            "modules": [],
        },
        registry,
    )
    baseline = [m["name"] for m in seeded["modules"]]

    expanded = expand_profile_seeds(
        {
            "schema_version": 2,
            "project": {"name": "demo"},
            "target": {"board": BOARD, "soc": SOC},
            "profile": f"{BOARD}_minimal",
            "modules": ["nsx-usb"],
        },
        registry,
    )
    names = [m["name"] for m in expanded["modules"]]

    # The board baseline is retained and the direct dep is layered on top.
    assert names[: len(baseline)] == baseline
    assert names[-1] == "nsx-usb"


# --- validation errors -----------------------------------------------------


def test_multiple_sources_on_one_entry_are_rejected() -> None:
    cfg = _base_cfg(
        modules=[{"name": "acme", "source": {"path": "../acme", "vendored": True}}]
    )
    with pytest.raises(NSXConfigError) as excinfo:
        NsxProject.from_mapping(cfg)

    assert excinfo.value.field == "modules[0].source"


def test_rev_without_git_is_rejected() -> None:
    cfg = _base_cfg(modules=[{"name": "acme", "source": {"rev": "main"}}])
    with pytest.raises(NSXConfigError) as excinfo:
        NsxProject.from_mapping(cfg)

    assert excinfo.value.field == "modules[0].source.rev"


def test_top_level_requires_is_rejected_with_migration_hint() -> None:
    cfg = _base_cfg(requires=["nsx-timer"])
    with pytest.raises(NSXConfigError, match="no longer supported") as excinfo:
        NsxProject.from_mapping(cfg)

    assert excinfo.value.field == "requires"


def test_per_target_requires_is_rejected() -> None:
    cfg = _base_cfg(
        targets={
            "default": BOARD,
            "supported": {BOARD: {"requires": ["nsx-timer"]}},
        },
    )
    with pytest.raises(NSXConfigError) as excinfo:
        NsxProject.from_mapping(cfg)

    assert excinfo.value.field == f"targets.supported.{BOARD}.requires"
