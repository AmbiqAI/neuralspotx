"""Byte-identical board.cmake contract guard (issue #154a, Phase 1).

The packaged ``boards/<board>/board.cmake`` files are being refactored from
monoliths into role fragments (``soc`` / ``bsp`` / ``memory`` / ``debug``)
behind a thin aggregator. That refactor must be **purely structural**: the
CMake state a board produces — the ordered sequence of target operations plus
every ``NSX_*`` variable it sets — has to stay identical.

These tests pin that contract. For every registered board and each toolchain
family, the packaged ``board.cmake`` is included in ``cmake -P`` script mode
through a harness that stubs all external commands (``nsx_*`` helpers and the
target commands, which are not scriptable anyway). Each stub appends a
deterministic line to a call log, so target creation, aliases, compile
definitions and link wiring all become comparable text. After the include the
harness dumps the call log followed by a sorted snapshot of all ``NSX_*``
variables. The combined capture is compared against a committed golden.

Regenerate goldens after an *intentional* behavior change with::

    NSX_REGEN_BOARD_CONTRACT=1 .venv/bin/python -m pytest \
        tests/test_board_cmake_contract.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

from neuralspotx import board_descriptors as bd

CMAKE = shutil.which("cmake")

pytestmark = pytest.mark.skipif(CMAKE is None, reason="cmake not available")

GOLDEN_DIR = Path(__file__).parent / "data" / "board_contract"
TOOLCHAIN_FAMILIES = ("gcc", "armclang")

# Fixed, path-stable inputs so the capture is deterministic across machines.
_STUB_ROOT = "/stub/app"
_STUB_SDK_ROOT = "/stub/ambiqsuite"

# Harness-provided input variables that are not board-produced state; excluded
# from the dumped snapshot so tmp paths never leak into the golden.
_INPUT_VARS = {"NSX_CMAKE_DIR"}

# Stubs for every external command a board.cmake may call. Each logs its
# invocation; a few also publish the outputs the board consumes downstream.
_STUBS = r"""
function(_logcall name)
    file(APPEND "${HARNESS_LOG}" "${name}: ${ARGN}\n")
endfunction()

function(nsx_load_soc_facts soc)
    _logcall("nsx_load_soc_facts" ${ARGV})
    # Deterministic placeholder SoC facts so any board consuming them is stable.
    set(NSX_SOC_NAME "${soc}" PARENT_SCOPE)
    set(NSX_CPU "stub-cpu" PARENT_SCOPE)
    set(NSX_FPU "stub-fpu" PARENT_SCOPE)
    set(NSX_FLOAT_ABI "stub-float-abi" PARENT_SCOPE)
    set(NSX_ABI_FLAGS "stub-abi-flags" PARENT_SCOPE)
endfunction()

function(nsx_soc_flags_target name)
    _logcall("nsx_soc_flags_target" ${ARGV})
endfunction()

function(nsx_module_dir_for_name out modname)
    _logcall("nsx_module_dir_for_name" ${ARGV})
    set(${out} "modules/${modname}" PARENT_SCOPE)
endfunction()

function(nsx_select_linker_script)
    cmake_parse_arguments(_sel "" "DEFAULT;ITCM" "" ${ARGN})
    _logcall("nsx_select_linker_script" ${ARGV})
    set(NSX_LINKER_SCRIPT "${_sel_DEFAULT}" PARENT_SCOPE)
endfunction()

function(nsx_assert_file_exists path)
    _logcall("nsx_assert_file_exists" ${ARGV})
endfunction()

function(nsx_apply_toolchain_flags target)
    _logcall("nsx_apply_toolchain_flags" ${ARGV})
endfunction()

# Target commands are not scriptable in cmake -P; shadowing them as functions
# both makes the include succeed and turns each into a comparable log line.
function(add_library)
    _logcall("add_library" ${ARGV})
endfunction()

function(set_target_properties)
    _logcall("set_target_properties" ${ARGV})
endfunction()

function(target_compile_definitions)
    _logcall("target_compile_definitions" ${ARGV})
endfunction()

function(target_compile_options)
    _logcall("target_compile_options" ${ARGV})
endfunction()

function(target_link_libraries)
    _logcall("target_link_libraries" ${ARGV})
endfunction()

function(target_link_options)
    _logcall("target_link_options" ${ARGV})
endfunction()

function(target_include_directories)
    _logcall("target_include_directories" ${ARGV})
endfunction()

function(install)
    _logcall("install" ${ARGV})
endfunction()
"""


def _board_dir(board: str) -> Path:
    pkg = resources.files("neuralspotx.boards") / board
    with resources.as_file(pkg) as path:
        return Path(path)


def _capture(tmp_path: Path, *, board: str, family: str) -> str:
    """Configure *board* via cmake -P and return its canonical contract dump."""
    src_dir = _board_dir(board)
    board_dir = tmp_path / "boards" / board
    board_dir.mkdir(parents=True)
    shutil.copytree(src_dir, board_dir, dirs_exist_ok=True)

    cmake_dir = tmp_path / "cmake"
    cmake_dir.mkdir()
    # Stub toolchain include: pins the family the board then branches on and
    # supplies nsx_apply_toolchain_flags (already stubbed, re-asserted here so
    # the real packaged file is never needed).
    (cmake_dir / "nsx_toolchain_flags.cmake").write_text(
        f'set(NSX_TOOLCHAIN_FAMILY "{family}")\n', encoding="utf-8"
    )

    log_file = tmp_path / "calls.log"
    out_file = tmp_path / "capture.txt"
    harness = tmp_path / "harness.cmake"
    harness.write_text(
        "\n".join(
            [
                f'set(HARNESS_LOG "{log_file.as_posix()}")',
                f'file(WRITE "{log_file.as_posix()}" "")',
                _STUBS,
                f'set(NSX_ROOT "{_STUB_ROOT}")',
                f'set(NSX_AMBIQSUITE_ROOT "{_STUB_SDK_ROOT}")',
                f'set(NSX_CMAKE_DIR "{cmake_dir.as_posix()}")',
                'set(NSX_SDK_PROVIDER "ambiqsuite")',
                f'include("{(board_dir / "board.cmake").as_posix()}")',
                "get_cmake_property(_all VARIABLES)",
                "list(SORT _all)",
                'set(_out "## CALLS\\n")',
                'file(READ "${HARNESS_LOG}" _calls)',
                'string(APPEND _out "${_calls}## VARS\\n")',
                "foreach(_v ${_all})",
                '    if(_v MATCHES "^NSX_")',
                '        string(APPEND _out "${_v}=${${_v}}\\n")',
                "    endif()",
                "endforeach()",
                f'file(WRITE "{out_file.as_posix()}" "${{_out}}")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [CMAKE, "-P", str(harness)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{board}/{family} configure failed:\n{result.stderr}"

    text = out_file.read_text(encoding="utf-8")
    # Drop harness-input vars so no tmp path leaks into the golden.
    kept = [
        line
        for line in text.splitlines()
        if not any(line.startswith(f"{v}=") for v in _INPUT_VARS)
    ]
    return "\n".join(kept) + "\n"


def _board_family_params() -> list:
    return [
        pytest.param(desc.name, family, id=f"{desc.name}-{family}")
        for desc in bd.list_boards()
        for family in TOOLCHAIN_FAMILIES
    ]


@pytest.mark.parametrize("board, family", _board_family_params())
def test_board_cmake_contract(tmp_path: Path, board: str, family: str) -> None:
    capture = _capture(tmp_path, board=board, family=family)
    golden = GOLDEN_DIR / f"{board}.{family}.txt"

    if os.environ.get("NSX_REGEN_BOARD_CONTRACT"):
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        golden.write_text(capture, encoding="utf-8")
        pytest.skip(f"regenerated golden for {board}/{family}")

    assert golden.exists(), (
        f"missing golden {golden.name}; regenerate with "
        f"NSX_REGEN_BOARD_CONTRACT=1"
    )
    assert capture == golden.read_text(encoding="utf-8"), (
        f"board.cmake contract drift for {board}/{family}"
    )
