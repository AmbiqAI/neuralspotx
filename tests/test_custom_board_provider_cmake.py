"""CMake-level provider inference for custom (inheriting) boards.

Regression guard for the custom-board provider flow:
``nsx board create <name> --from <evb>`` scaffolds a thin
``boards/<name>/board.cmake`` plus a declarative ``board.yaml`` with
``inherits: <evb>``. SDK provider selection runs (in ``nsx_bootstrap_app``)
*before* any ``board.cmake`` is included, and the generated board table only
knows the registered EVBs. Provider inference therefore has to follow the
descriptor's ``inherits`` link, not scrape parent data out of generated CMake.

These tests drive the real packaged CMake in ``cmake -P`` script mode, so
they exercise ``nsx_select_sdk_provider`` end to end without a firmware
build or toolchain.
"""

from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

from neuralspotx import board_descriptors as bd

CMAKE = shutil.which("cmake")

pytestmark = pytest.mark.skipif(CMAKE is None, reason="cmake not available")


def _providers_cmake(tmp_path: Path) -> Path:
    """Copy the packaged cmake dir into *tmp_path* and return the providers file.

    The providers script ``include()``s ``nsx_board_table.cmake`` from its
    own directory, so both files must sit together.
    """
    dest = tmp_path / "cmake"
    dest.mkdir()
    pkg = resources.files("neuralspotx.cmake")
    for name in ("nsx_sdk_providers.cmake", "nsx_board_table.cmake"):
        src = pkg.joinpath(name)
        with resources.as_file(src) as path:
            (dest / name).write_text(
                Path(path).read_text(encoding="utf-8"), encoding="utf-8"
            )
    return dest / "nsx_sdk_providers.cmake"


def _scaffold_custom_board(nsx_root: Path, name: str, parent: str) -> None:
    board_dir = nsx_root / "boards" / name
    board_dir.mkdir(parents=True)
    board_dir.joinpath("board.yaml").write_text(
        bd.render_custom_board_yaml(name=name, parent=parent),
        encoding="utf-8",
    )
    board_dir.joinpath("board.cmake").write_text(
        bd.render_custom_board_cmake(name=name, parent=parent),
        encoding="utf-8",
    )


def _run_select(tmp_path: Path, *, board: str, nsx_root: Path) -> subprocess.CompletedProcess:
    """Invoke ``nsx_select_sdk_provider(board)`` via cmake script mode."""
    providers = _providers_cmake(tmp_path)
    # A dummy AmbiqSuite root so the post-inference root existence check in
    # nsx_select_sdk_provider passes regardless of where the module is
    # vendored.
    sdk_root = tmp_path / "sdk_root"
    sdk_root.mkdir(exist_ok=True)
    harness = tmp_path / "harness.cmake"
    harness.write_text(
        "\n".join(
            [
                f'set(NSX_ROOT "{nsx_root.as_posix()}")',
                f'include("{providers.as_posix()}")',
                f'nsx_select_sdk_provider("{board}")',
                'message(STATUS "RESOLVED_PROVIDER=${NSX_SDK_PROVIDER}")',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [
            CMAKE,
            f"-DNSX_AMBIQSUITE_ROOT_OVERRIDE={sdk_root.as_posix()}",
            "-P",
            str(harness),
        ],
        capture_output=True,
        text=True,
    )


def test_custom_board_inherits_parent_provider(tmp_path: Path) -> None:
    nsx_root = tmp_path / "app"
    _scaffold_custom_board(nsx_root, "my_apollo510", "apollo510_evb")

    result = _run_select(tmp_path, board="my_apollo510", nsx_root=nsx_root)

    assert result.returncode == 0, result.stderr
    assert "RESOLVED_PROVIDER=ambiqsuite" in result.stdout + result.stderr


def test_custom_board_inherits_r4_parent_provider(tmp_path: Path) -> None:
    nsx_root = tmp_path / "app"
    _scaffold_custom_board(nsx_root, "my_apollo4p", "apollo4p_evb")

    result = _run_select(tmp_path, board="my_apollo4p", nsx_root=nsx_root)

    assert result.returncode == 0, result.stderr
    assert "RESOLVED_PROVIDER=ambiqsuite" in result.stdout + result.stderr


def test_registered_evb_still_resolves_directly(tmp_path: Path) -> None:
    nsx_root = tmp_path / "app"
    (nsx_root / "boards").mkdir(parents=True)

    result = _run_select(tmp_path, board="apollo510_evb", nsx_root=nsx_root)

    assert result.returncode == 0, result.stderr
    assert "RESOLVED_PROVIDER=ambiqsuite" in result.stdout + result.stderr


def test_unknown_board_without_parent_still_errors(tmp_path: Path) -> None:
    nsx_root = tmp_path / "app"
    (nsx_root / "boards").mkdir(parents=True)

    result = _run_select(tmp_path, board="not_a_real_board", nsx_root=nsx_root)

    assert result.returncode != 0
    assert "Unable to infer SDK provider" in result.stdout + result.stderr


def test_provider_parent_comes_from_board_yaml_not_board_cmake(tmp_path: Path) -> None:
    nsx_root = tmp_path / "app"
    _scaffold_custom_board(nsx_root, "my_apollo510", "apollo510_evb")
    board_dir = nsx_root / "boards" / "my_apollo510"
    board_dir.joinpath("board.cmake").write_text(
        bd.render_custom_board_cmake(name="my_apollo510", parent="not_a_real_board"),
        encoding="utf-8",
    )

    result = _run_select(tmp_path, board="my_apollo510", nsx_root=nsx_root)

    assert result.returncode == 0, result.stderr
    assert "RESOLVED_PROVIDER=ambiqsuite" in result.stdout + result.stderr
