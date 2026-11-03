"""Real CMake regressions for independent build inputs; no SDK/network needed."""

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from neuralspotx.operations._lock import lock_app_impl
from neuralspotx.operations._sync import regenerate_active_board_glue

BOARDS = ("apollo510_evb", "apollo510b_evb")


def cmake(*args: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("cmake")
    if executable is None:
        pytest.skip("CMake required")
    return subprocess.run([executable, *args], capture_output=True, text=True, check=False)


@pytest.fixture
def app(tmp_path: Path) -> Path:
    cfg = {
        "schema_version": 2,
        "project": {"name": "isolated"},
        "targets": {"default": BOARDS[0], "supported": list(BOARDS)},
        "baseline": "none",
        "modules": [
            {"name": name, "source": {"vendored": True}, "boards": [board]}
            for name, board in zip(("alpha", "beta"), BOARDS, strict=True)
        ],
    }
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    for name in ("alpha", "beta"):
        folder = tmp_path / "modules" / name
        folder.mkdir(parents=True)
        (folder / "CMakeLists.txt").write_text(f"add_library({name} INTERFACE)\n", encoding="utf-8")
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\nproject(isolated NONE)\n"
        'include("${CMAKE_SOURCE_DIR}/cmake/nsx/modules.cmake")\n'
        "foreach(module IN LISTS NSX_APP_MODULES)\n"
        '  add_subdirectory("modules/${module}" "modules/${module}")\n'
        "endforeach()\n"
        'if(NSX_BOARD STREQUAL "apollo510_evb")\n'
        "  if(NOT TARGET alpha OR TARGET beta)\n"
        '    message(FATAL_ERROR "wrong closure for alpha")\n'
        "  endif()\n"
        "else()\n"
        "  if(NOT TARGET beta OR TARGET alpha)\n"
        '    message(FATAL_ERROR "wrong closure for beta")\n'
        "  endif()\n"
        "endif()\n",
        encoding="utf-8",
    )
    lock_app_impl(tmp_path)
    return tmp_path


def configure(app: Path, build: Path, board: str) -> None:
    regenerate_active_board_glue(app, board, build_dir=build)
    result = cmake("-S", str(app), "-B", str(build), f"-DNSX_BOARD={board}")
    assert result.returncode == 0, result.stdout + result.stderr


def test_alternating_custom_builds_and_plain_reconfigure(app: Path) -> None:
    first = app / "custom-a"
    second = app / "custom-b"
    configure(app, first, BOARDS[0])
    snapshot = (first / "nsx/modules.cmake").read_bytes()
    configure(app, second, BOARDS[1])
    assert (first / "nsx/modules.cmake").read_bytes() == snapshot
    # Exercise CMake's own reconfigure without a Python refresh after B.
    result = cmake("-S", str(app), "-B", str(first))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "alpha" not in (app / "cmake/nsx/modules.cmake").read_text()
    assert "beta" not in (app / "cmake/nsx/modules.cmake").read_text()


def test_concurrent_configure_of_distinct_closures(app: Path) -> None:
    def task(board: str) -> None:
        configure(app, app / "build" / board, board)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(task, BOARDS))
    for board in BOARDS:
        result = cmake("--build", str(app / "build" / board))
        assert result.returncode == 0, result.stdout + result.stderr


def test_missing_and_mismatched_inputs_are_actionable(app: Path) -> None:
    build = app / "unprepared"
    result = cmake("-S", str(app), "-B", str(build), f"-DNSX_BOARD={BOARDS[0]}")
    assert result.returncode != 0
    assert "nsx configure" in result.stderr
    configure(app, build, BOARDS[0])
    result = cmake("-S", str(app), "-B", str(build), f"-DNSX_BOARD={BOARDS[1]}")
    assert result.returncode != 0
    assert "module inputs belong to" in result.stderr
    configure(app, build, BOARDS[1])


def test_manifest_board_case_uses_canonical_identity_and_path(app: Path) -> None:
    from neuralspotx.project_config import _write_app_module_file

    cfg = yaml.safe_load((app / "nsx.yml").read_text())
    cfg["target"] = {"board": "APOLLO510_EVB"}
    _write_app_module_file(app, cfg, module_names=["alpha"])
    build = app / "build" / BOARDS[0]
    # Inspect stored spelling; exists() folds case on Windows and macOS.
    assert "APOLLO510_EVB" not in {path.name for path in (app / "build").iterdir()}
    result = cmake("-S", str(app), "-B", str(build), f"-DNSX_BOARD={BOARDS[0]}")
    assert result.returncode == 0, result.stdout + result.stderr
