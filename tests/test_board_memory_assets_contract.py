"""Cross-repo contract: board.cmake memory assets must exist in nsx-core.

Every packaged ``boards/<board>/memory.cmake`` names startup sources and
linker scripts under the vendored ``nsx-core`` module
(``modules/nsx-core/src/<soc>/<toolchain>/...``). Those paths are captured in
the ``tests/data/board_contract/*.txt`` goldens as
``/stub/app/modules/nsx-core/...`` references. A board can pass the
``cmake -P`` contract harness (which stubs ``nsx_assert_file_exists``) while
pointing at a file the SDK never shipped -- that fails late, at real configure
time, for every user. This test resolves each referenced path against an SDK
checkout so the drift is caught here.

Only toolchain families a board declares in its ``board.yaml`` are checked:
the contract harness captures every board under both ``gcc`` and
``armclang`` regardless, but a family the board does not offer (e.g. the
armclang branch of a gcc-only Apollo2/Apollo4 board) is not a shipped
contract and is skipped with that reason.

It is skipped when the SDK module is not available (NSX unit CI does not
vendor it). Locate the SDK via ``NSX_AMBIQ_SDK_ROOT`` or a checkout adjacent
to the neuralspotx repo (``<workspace>/nsx-modules/nsx-ambiq-sdk``), the same
discovery as ``test_board_cpu_facts_contract.py``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from neuralspotx import board_descriptors as bd

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN_DIR = _REPO_ROOT / "tests" / "data" / "board_contract"

# The harness roots the app at this path; nsx-core is vendored beneath it.
_STUB_NSX_CORE_PREFIX = "/stub/app/modules/nsx-core/"
_STUB_NSX_CORE_RE = re.compile(re.escape(_STUB_NSX_CORE_PREFIX) + r"([^\s;\"]+)")

# board.yaml toolchain name -> the NSX_TOOLCHAIN_FAMILY branch board.cmake
# takes for it. ``atfe`` is its own family but every packaged board routes it
# through the gcc (``else``) asset branch.
_TOOLCHAIN_FAMILY = {
    "arm-none-eabi-gcc": "gcc",
    "gcc": "gcc",
    "atfe": "gcc",
    "armclang": "armclang",
}


def _declared_families(board: str) -> set[str]:
    desc = bd.load_board(board)
    if desc is None:
        return set()
    return {_TOOLCHAIN_FAMILY[tc] for tc in desc.toolchains if tc in _TOOLCHAIN_FAMILY}


def _sdk_root() -> Path | None:
    roots: list[Path] = []
    env_root = os.environ.get("NSX_AMBIQ_SDK_ROOT")
    if env_root:
        roots.append(Path(env_root))
    # Default: a sibling checkout under the surrounding workspace.
    roots.append(_REPO_ROOT.parent / "nsx-modules" / "nsx-ambiq-sdk")
    for root in roots:
        if (root / "modules" / "nsx-core" / "nsx-module.yaml").is_file():
            return root
    return None


_SDK_ROOT = _sdk_root()

pytestmark = pytest.mark.skipif(
    _SDK_ROOT is None,
    reason=(
        "nsx-ambiq-sdk checkout not available; set NSX_AMBIQ_SDK_ROOT or check "
        "out the SDK module adjacent to the repo"
    ),
)


def _golden_params() -> list:
    return [pytest.param(path, id=path.stem) for path in sorted(_GOLDEN_DIR.glob("*.txt"))]


def _referenced_nsx_core_paths(golden: Path) -> set[str]:
    return set(_STUB_NSX_CORE_RE.findall(golden.read_text(encoding="utf-8")))


def test_goldens_reference_nsx_core_assets() -> None:
    """Sanity: the extraction regex actually finds paths in the goldens."""

    goldens = sorted(_GOLDEN_DIR.glob("*.txt"))
    assert goldens, f"no board-contract goldens under {_GOLDEN_DIR}"
    assert any(_referenced_nsx_core_paths(g) for g in goldens)


@pytest.mark.parametrize("golden", _golden_params())
def test_board_memory_assets_exist_in_nsx_core(golden: Path) -> None:
    assert _SDK_ROOT is not None  # narrowed by the module-level skip guard
    board, family = golden.stem.rsplit(".", 1)
    declared = _declared_families(board)
    assert declared, f"{board}: not a registered board or declares no toolchain"
    if family not in declared:
        pytest.skip(f"{board} does not declare a {family}-family toolchain in board.yaml")
    nsx_core = _SDK_ROOT / "modules" / "nsx-core"
    referenced = _referenced_nsx_core_paths(golden)
    assert referenced, f"{golden.name}: no nsx-core assets referenced (harness drift?)"
    missing = sorted(rel for rel in referenced if not (nsx_core / rel).is_file())
    assert not missing, (
        f"{golden.name} references nsx-core files absent from {nsx_core}:\n  "
        + "\n  ".join(missing)
    )
