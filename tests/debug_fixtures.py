"""Small real CMake apps for host-only debug integration tests."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake"


def cmake(*args: str | Path) -> None:
    result = subprocess.run(["cmake", *map(str, args)], capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


def make_debug_app(
    app: Path, board: str = "apollo510_evb", build: Path | None = None
) -> tuple[Path, Path]:
    if (
        not shutil.which("cmake")
        or not shutil.which("ninja")
        or not (shutil.which("cc") or shutil.which("cl"))
    ):
        pytest.skip("native compiler, Ninja and CMake >=3.31 required")
    version = subprocess.check_output(["cmake", "--version"], text=True).split()[2]
    if tuple(map(int, version.split(".")[:2])) < (3, 31):
        pytest.skip("CMake >=3.31 required")
    app.mkdir(parents=True, exist_ok=True)
    build = build or app / "build" / board
    shutil.copytree(ROOT, app / "cmake/nsx", dirs_exist_ok=True)
    (app / "nsx.yml").write_text(
        f"schema_version: 2\nproject:\n  name: demo\ntargets:\n  default: {board}\n  supported: [{board}, apollo510_evb]\nbaseline: none\n"
    )
    (app / "main.c").write_text(
        "unsigned char _SEGGER_RTT[1024]; int main(void) {return _SEGGER_RTT[0];}\n"
    )
    (app / "board.cmake").write_text(
        "set(NSX_SEGGER_DEVICE CustomDevice)\nset(NSX_SEGGER_IF_SPEED 1200)\n"
    )
    (app / "CMakeLists.txt").write_text("""cmake_minimum_required(VERSION 3.31)
project(demo C)
set(NSX_DEBUG_CONTEXT ON CACHE BOOL "debug")
set(NSX_DEBUG_INPUT_CONTRACT 1)
set(NSX_JLINK_SERIAL 1234 CACHE STRING "probe")
set(NSX_CMAKE_DIR "${CMAKE_SOURCE_DIR}/cmake/nsx")
set(NSX_JLINK_EXE "${CMAKE_COMMAND}")
set(NSX_JLINK_SWO_EXE "${CMAKE_COMMAND}")
set(NSX_SEGGER_PF_ADDR 0x1000)
set(NSX_SEGGER_CPUFREQ 96000000)
set(NSX_SEGGER_SWOFREQ 1000000)
include(cmake/nsx/nsx_helpers.cmake)
include(board.cmake)
add_executable(demo main.c)
set_target_properties(demo PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/firmware output")
add_custom_command(TARGET demo POST_BUILD COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:demo> $<TARGET_FILE_DIR:demo>/demo.bin)
nsx_add_segger_targets(demo)
nsx_debug_set_primary_target(demo)
""")
    cmake("-S", app, "-B", build, "-G", "Ninja", f"-DNSX_BOARD:STRING={board}")
    prepare(app, build)
    cmake("--build", build)
    return app, build


def prepare(app: Path, build: Path) -> None:
    cmake(f"-DNSX_DEBUG_BUILD_DIR={build}", "-P", app / "cmake/nsx/nsx_debug_prepare.cmake")
