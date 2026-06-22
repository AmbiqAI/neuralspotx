"""Step 5: per-target source/linker overlay CMake helpers (#135 step 5).

These guard the contract of the overlay helpers without requiring a full
CMake configure (which needs a cross toolchain): the helpers must exist in
the canonical app bootstrap, and the power_benchmark example must consume
the linker-overlay helper rather than hand-rolling the board-flags swap.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO_ROOT / "src" / "neuralspotx" / "cmake" / "nsx_app_bootstrap.cmake"
POWER_BENCHMARK = REPO_ROOT / "examples" / "power_benchmark" / "CMakeLists.txt"


def test_bootstrap_defines_overlay_helpers() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "function(nsx_target_soc_overlay app_target)" in text
    assert "function(nsx_target_linker_overlay app_target script_path)" in text


def test_soc_overlay_globs_by_soc_family() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    # Overlay directory is keyed by the active board's SoC family.
    assert "src/${NSX_SOC_FAMILY}" in text
    # No-op guard when the family or overlay dir is absent.
    assert "IS_DIRECTORY" in text


def test_linker_overlay_filters_and_appends_dash_t() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'list(FILTER _link_opts EXCLUDE REGEX "^-T")' in text
    assert "INTERFACE_LINK_OPTIONS" in text
    # armclang scatter overlay is explicitly unsupported (warns, no-op).
    assert "armclang scatter overlay not supported" in text


def test_power_benchmark_uses_linker_overlay_helper() -> None:
    text = POWER_BENCHMARK.read_text(encoding="utf-8")
    assert "nsx_target_linker_overlay(power_benchmark" in text
    # The bespoke inline swap should be gone.
    assert "INTERFACE_LINK_OPTIONS ${_board_link_opts}" not in text
