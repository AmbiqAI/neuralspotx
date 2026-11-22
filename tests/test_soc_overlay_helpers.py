"""Board linker-input and source overlay contracts for generated apps."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("compiler", ["GNU", "Clang", "ARMClang"])
def test_active_linker_script_is_a_link_dependency(tmp_path: Path, compiler: str) -> None:
    cmake = shutil.which("cmake")
    if not cmake:
        pytest.skip("CMake is required for the board linker contract")
    (tmp_path / "CMakeLists.txt").write_text(
        f"""cmake_minimum_required(VERSION 3.24)
project(check NONE)
include("{BOOTSTRAP.as_posix()}")
set(CMAKE_C_COMPILER_ID {compiler})
include("{(BOOTSTRAP.parent / "nsx_toolchain_flags.cmake").as_posix()}")
set(NSX_BOARD demo)
set(NSX_LINKER_SCRIPT "${{CMAKE_CURRENT_SOURCE_DIR}}/board.ld")
add_library(nsx_board_demo_flags INTERFACE)
add_library(app INTERFACE)
set_property(TARGET nsx_board_demo_flags PROPERTY INTERFACE_LINK_DEPENDS other-input)
nsx_apply_toolchain_flags(nsx_board_demo_flags)
function(record stage)
    get_property(deps TARGET nsx_board_demo_flags PROPERTY INTERFACE_LINK_DEPENDS)
    file(WRITE "${{CMAKE_BINARY_DIR}}/${{stage}}" "${{deps}}")
endfunction()
record(initial)
foreach(name IN ITEMS first second)
    file(WRITE "${{CMAKE_CURRENT_SOURCE_DIR}}/${{name}} overlay.ld" "")
    nsx_target_linker_overlay(app "${{CMAKE_CURRENT_SOURCE_DIR}}/${{name}} overlay.ld")
    record(${{name}})
endforeach()
""",
        encoding="utf-8",
    )
    build = tmp_path / "build"
    subprocess.run([cmake, "-S", str(tmp_path), "-B", str(build)], check=True)
    for stage in ("initial", "first", "second"):
        script = (
            "board.ld" if stage == "initial" or compiler == "ARMClang" else f"{stage} overlay.ld"
        )
        assert (build / stage).read_text().split(";") == [
            "other-input",
            (tmp_path / script).as_posix(),
        ]
