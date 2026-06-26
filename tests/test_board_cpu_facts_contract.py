"""Cross-repo contract: board.yaml CPU facts must match the SDK SoC facts.

The build-time CPU/ABI truth lives in the ``nsx-ambiq-sdk`` module's
``cmake/socs/facts/<soc>.cmake`` (``NSX_CPU`` / ``NSX_FLOAT_ABI`` /
``NSX_ABI_FLAGS``). The ``cpu`` block in each NSX ``board.yaml`` is a
descriptor-facing copy consumed by ``nsx board info``. This test guards the
two from silently drifting.

It is skipped when the SDK module is not available (NSX unit CI does not
vendor it). Locate the SDK via ``NSX_AMBIQ_SDK_FACTS_DIR`` or
``NSX_AMBIQ_SDK_ROOT``, or by a checkout adjacent to the neuralspotx repo
(``<workspace>/nsx-modules/nsx-ambiq-sdk``).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from neuralspotx import board_descriptors as bd

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _sdk_facts_dir() -> Path | None:
    explicit = os.environ.get("NSX_AMBIQ_SDK_FACTS_DIR")
    if explicit:
        d = Path(explicit)
        return d if d.is_dir() else None

    roots: list[Path] = []
    env_root = os.environ.get("NSX_AMBIQ_SDK_ROOT")
    if env_root:
        roots.append(Path(env_root))
    # Default: a sibling checkout under the surrounding workspace.
    roots.append(_REPO_ROOT.parent / "nsx-modules" / "nsx-ambiq-sdk")
    for root in roots:
        facts = root / "cmake" / "socs" / "facts"
        if facts.is_dir():
            return facts
    return None


_FACTS_DIR = _sdk_facts_dir()

_SET_RE = re.compile(r'^\s*set\(\s*(\w+)\s+"([^"]*)"\s*\)', re.MULTILINE)


def _parse_facts(path: Path) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in _SET_RE.finditer(path.read_text(encoding="utf-8"))
    }


pytestmark = pytest.mark.skipif(
    _FACTS_DIR is None,
    reason=(
        "nsx-ambiq-sdk SoC facts not available; set NSX_AMBIQ_SDK_ROOT / "
        "NSX_AMBIQ_SDK_FACTS_DIR or check out the SDK module adjacent to the repo"
    ),
)


def test_board_cpu_matches_sdk_soc_facts() -> None:
    assert _FACTS_DIR is not None  # narrowed by the skip guard above
    missing_facts: list[str] = []
    mismatches: list[str] = []
    for name, desc in sorted(bd.load_board_descriptors().items()):
        facts_path = _FACTS_DIR / f"{desc.soc}.cmake"
        if not facts_path.is_file():
            missing_facts.append(f"{name}: no SDK SoC facts file '{facts_path.name}'")
            continue
        facts = _parse_facts(facts_path)
        expected = {
            "core": facts.get("NSX_CPU"),
            "float_abi": facts.get("NSX_FLOAT_ABI"),
            "abi": facts.get("NSX_ABI_FLAGS"),
        }
        actual = {
            "core": desc.cpu.core,
            "float_abi": desc.cpu.float_abi,
            "abi": desc.cpu.abi,
        }
        if actual != expected:
            mismatches.append(
                f"{name} (soc={desc.soc}): board.yaml={actual} vs sdk={expected}"
            )

    assert not missing_facts, "boards reference SoCs without SDK facts:\n" + "\n".join(
        missing_facts
    )
    assert not mismatches, "board.yaml cpu drifted from SDK SoC facts:\n" + "\n".join(
        mismatches
    )


# SoCs that legitimately ship SDK facts without a matching NSX board. These are
# in-development parts (no production EVB yet). ``atomiq110`` / AT110 is bring-up
# on an FPGA only. Extend this set (with justification) when the SDK adds a new
# SoC ahead of its board, or remove an entry once a board lands for it.
ALLOWED_SOCS_WITHOUT_BOARD = frozenset({"atomiq110"})


def test_soc_inventory_symmetry() -> None:
    """B6: keep the board↔SoC-facts inventory symmetric.

    Two directions:

    * **board → facts (hard):** every board's ``soc`` must resolve to an SDK
      facts file. This is the fast Python-level guard the arch review asked
      for — a missing facts file is caught here instead of failing late inside
      ``nsx_load_soc_facts("<soc>")`` at CMake configure time.
    * **facts → board (allow-listed):** any SoC facts file *without* a matching
      board must be an explicitly allow-listed in-development part, so new
      asymmetry introduced by an SDK update is surfaced for review rather than
      silently accumulating.

    Matching is by ``soc`` (not board name), so name divergences like
    ``apollo510dL_evb`` → ``apollo510L`` are handled correctly.
    """
    assert _FACTS_DIR is not None  # narrowed by the module-level skip guard
    board_socs = {desc.soc for desc in bd.load_board_descriptors().values()}
    facts_socs = {p.stem for p in _FACTS_DIR.glob("*.cmake")}

    boards_without_facts = sorted(board_socs - facts_socs)
    assert not boards_without_facts, (
        "boards target SoCs with no SDK facts file (would fail late at CMake "
        "configure in nsx_load_soc_facts):\n  " + "\n  ".join(boards_without_facts)
    )

    facts_without_boards = sorted(facts_socs - board_socs - ALLOWED_SOCS_WITHOUT_BOARD)
    assert not facts_without_boards, (
        "SDK SoC facts exist with no NSX board and are not allow-listed — add a "
        "board.yaml or extend ALLOWED_SOCS_WITHOUT_BOARD:\n  "
        + "\n  ".join(facts_without_boards)
    )
