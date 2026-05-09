"""Case-insensitive board/SoC normalization at NSX input boundaries.

Background: ``apollo330mP_evb`` carries a load-bearing capital ``P`` (it
maps to a filesystem directory, a CMake target alias, and an
``nsx-modules`` package name) and cannot be safely lowercased.  Most
other canonical board names *are* lowercase.  Users routinely typo the
case (``APOLLO510_EVB``, ``Apollo330mp_EVB``), so NSX silently maps any
case-insensitive input to the canonical spelling at every boundary
(CLI args, ``nsx.yml`` load, public API).  CMake mirrors this with a
defensive ``string(TOLOWER ...)`` in ``nsx_sdk_providers.cmake``.

This module pins:

  * Round-trip normalization for every canonical board / SoC across
    lower / upper / random-mixed / identity casings.
  * Unknown inputs pass through unchanged (downstream errors surface
    domain-specific messages).
  * Drift guard: every board key in ``DEFAULT_SOC_FOR_BOARD`` is
    represented (lowercased) in the packaged ``nsx_sdk_providers.cmake``
    branch list and vice versa.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

import pytest

from neuralspotx.constants import (
    BOARDS,
    DEFAULT_SOC_FOR_BOARD,
    SOCS,
    normalize_board,
    normalize_soc,
)

# ---------------------------------------------------------------------------
# Case-insensitive normalization
# ---------------------------------------------------------------------------


CASING_VARIANTS = (str.lower, str.upper, lambda s: s.swapcase(), lambda s: s)


@pytest.mark.parametrize("canonical", BOARDS)
@pytest.mark.parametrize("recase", CASING_VARIANTS)
def test_normalize_board_round_trips(canonical: str, recase) -> None:
    assert normalize_board(recase(canonical)) == canonical


@pytest.mark.parametrize("canonical", SOCS)
@pytest.mark.parametrize("recase", CASING_VARIANTS)
def test_normalize_soc_round_trips(canonical: str, recase) -> None:
    assert normalize_soc(recase(canonical)) == canonical


def test_normalize_board_passthrough_for_unknown() -> None:
    # Unknown inputs are returned unchanged so downstream error paths
    # (board.cmake selection, SoC inference) can produce a domain-specific
    # message.
    assert normalize_board("not_a_real_board") == "not_a_real_board"


def test_normalize_soc_passthrough_for_unknown() -> None:
    assert normalize_soc("not_a_real_soc") == "not_a_real_soc"


def test_normalize_board_handles_empty_and_none() -> None:
    assert normalize_board("") == ""
    assert normalize_board(None) is None


def test_normalize_soc_handles_empty_and_none() -> None:
    assert normalize_soc("") == ""
    assert normalize_soc(None) is None


def test_lowercase_alias_no_longer_in_default_soc_map() -> None:
    # Hack alias removed in favour of normalize_board().
    assert "apollo330mp_evb" not in DEFAULT_SOC_FOR_BOARD
    assert "apollo330mP_evb" in DEFAULT_SOC_FOR_BOARD


# ---------------------------------------------------------------------------
# Drift guard between Python board map and packaged CMake provider list
# ---------------------------------------------------------------------------


def _packaged_cmake_text() -> str:
    pkg = resources.files("neuralspotx.cmake").joinpath("nsx_sdk_providers.cmake")
    with resources.as_file(pkg) as path:
        return Path(path).read_text(encoding="utf-8")


def test_cmake_provider_list_matches_python_board_map() -> None:
    text = _packaged_cmake_text()
    # The selector compares the lowercased board against literal strings
    # like `_board_lc STREQUAL "apollo510_evb"`.  Pull all such literals.
    cmake_boards = {m.lower() for m in re.findall(r'_board_lc\s+STREQUAL\s+"([^"]+)"', text)}
    py_boards = {b.lower() for b in BOARDS}
    assert cmake_boards == py_boards, (
        f"CMake/Python board lists drifted.\n"
        f"  in CMake only: {sorted(cmake_boards - py_boards)}\n"
        f"  in Python only: {sorted(py_boards - cmake_boards)}"
    )
