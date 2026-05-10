"""Drift guard for the generated CMake board → SDK provider table.

The committed ``src/neuralspotx/cmake/nsx_board_table.cmake`` must
exactly match the output of ``scripts/gen_board_table.py`` rendered
from ``BOARD_SDK_PROVIDER`` in :mod:`neuralspotx.constants`.

If this test fails, run::

    python scripts/gen_board_table.py

and commit the regenerated file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from neuralspotx.constants import BOARD_SDK_PROVIDER, BOARDS, SDK_PROVIDERS

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = REPO_ROOT / "scripts" / "gen_board_table.py"
TABLE_FILE = REPO_ROOT / "src" / "neuralspotx" / "cmake" / "nsx_board_table.cmake"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_board_table", GEN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_boards_have_a_provider() -> None:
    """Every canonical board must map to a known SDK provider."""

    missing = [b for b in BOARDS if b not in BOARD_SDK_PROVIDER]
    assert not missing, f"BOARDS without BOARD_SDK_PROVIDER entry: {missing}"

    unknown = {b: p for b, p in BOARD_SDK_PROVIDER.items() if p not in SDK_PROVIDERS}
    assert not unknown, f"BOARD_SDK_PROVIDER values not in SDK_PROVIDERS: {unknown}"

    extra = [b for b in BOARD_SDK_PROVIDER if b not in BOARDS]
    assert not extra, f"BOARD_SDK_PROVIDER has boards not in BOARDS: {extra}"


def test_committed_cmake_table_matches_generator_output() -> None:
    """The committed CMake table must equal freshly rendered output."""

    gen = _load_generator()
    expected = gen.render()
    actual = TABLE_FILE.read_text()
    assert actual == expected, (
        "nsx_board_table.cmake is stale. "
        "Run `python scripts/gen_board_table.py` and commit the result."
    )
