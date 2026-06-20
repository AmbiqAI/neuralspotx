"""Tests for the first-class board descriptors (``board.yaml``).

These guard that the packaged descriptors stay well-formed and that the
legacy ``constants`` tables remain a faithful derivation of them.
"""

from __future__ import annotations

from neuralspotx import board_descriptors as bd
from neuralspotx.constants import (
    _BOARD_ORDER,
    BOARD_SDK_PROVIDER,
    DEFAULT_SOC_FOR_BOARD,
    SDK_PROVIDERS,
)


def test_every_board_dir_ships_a_descriptor() -> None:
    """Each ``boards/<name>/`` directory must provide a ``board.yaml``."""

    dirs = {p.name for p in bd.BOARDS_DIR.iterdir() if (p / "board.cmake").is_file()}
    descriptors = set(bd.load_board_descriptors())
    missing = dirs - descriptors
    assert not missing, f"board directories without board.yaml: {sorted(missing)}"


def test_descriptor_name_matches_directory() -> None:
    for name, desc in bd.load_board_descriptors().items():
        assert desc.path.name == name


def test_registered_set_matches_board_order() -> None:
    """``_BOARD_ORDER`` must equal exactly the set of registered boards."""

    registered = {
        name for name, desc in bd.load_board_descriptors().items() if desc.registered
    }
    assert registered == set(_BOARD_ORDER)


def test_default_soc_table_is_derived_from_descriptors() -> None:
    descriptors = bd.load_board_descriptors()
    expected = {b: descriptors[b].soc for b in _BOARD_ORDER}
    assert DEFAULT_SOC_FOR_BOARD == expected
    # Order is load-bearing for the generated CMake table.
    assert list(DEFAULT_SOC_FOR_BOARD) == list(_BOARD_ORDER)


def test_provider_table_is_derived_from_descriptors() -> None:
    descriptors = bd.load_board_descriptors()
    expected = {b: descriptors[b].sdk_provider for b in _BOARD_ORDER}
    assert BOARD_SDK_PROVIDER == expected
    assert list(BOARD_SDK_PROVIDER) == list(_BOARD_ORDER)


def test_registered_providers_are_known() -> None:
    for desc in bd.list_boards(registered_only=True):
        assert desc.sdk_provider in SDK_PROVIDERS


def test_unregistered_board_excluded_from_legacy_tables() -> None:
    """A descriptor with ``registered: false`` stays out of the dicts."""

    unregistered = [
        d.name for d in bd.load_board_descriptors().values() if not d.registered
    ]
    for name in unregistered:
        assert name not in DEFAULT_SOC_FOR_BOARD
        assert name not in BOARD_SDK_PROVIDER


def test_load_board_returns_descriptor_with_cpu() -> None:
    desc = bd.load_board("apollo510_evb")
    assert desc is not None
    assert desc.soc == "apollo510"
    assert desc.sdk_provider == "ambiqsuite"
    assert desc.cpu.core == "cortex-m55"
    assert "arm-none-eabi-gcc" in desc.toolchains


def test_load_board_unknown_returns_none() -> None:
    assert bd.load_board("no_such_board") is None
