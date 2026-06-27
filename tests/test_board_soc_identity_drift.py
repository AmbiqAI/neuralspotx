"""Board SoC-identity drift guard (issue arch-review B1).

The SoC string for a board is declared in ``board.yaml`` (``board.soc``) and
restated in the board's ``soc.cmake`` role fragment as the argument to
``nsx_load_soc_facts("<soc>")`` — the call that loads the SDK's authoritative
SoC facts. Those two must agree, otherwise ``board info`` (Python) and the
build (CMake) silently disagree about which silicon a board targets.

This is the low-risk first step of B1: a pure in-repo drift guard. It does not
refactor the fragments. The companion check that the resolved SoC actually has
an SDK facts file lives in ``tests/test_board_cpu_facts_contract.py`` (skipped
when the SDK module is absent).

Note the BSP layer is intentionally *not* asserted here: ``NSX_AMBIQ_PART_NAME``
in ``bsp.cmake`` is a board/BSP-owned fact that can legitimately differ from the
SoC (e.g. ``apollo510b_evb`` loads ``apollo510b`` SoC facts but uses the
``apollo510`` MCU/BSP directory). Only the SoC-owned ``nsx_load_soc_facts``
argument is part of the SoC-identity contract.
"""

from __future__ import annotations

import re

from neuralspotx import board_descriptors as bd

# Match the real ``nsx_load_soc_facts("…")`` call (line start, after optional
# indentation) so commented references do not match.
_LOAD_SOC_FACTS_RE = re.compile(
    r'^\s*nsx_load_soc_facts\(\s*"([^"]+)"\s*\)', re.MULTILINE
)


def test_board_yaml_soc_matches_soc_cmake_load() -> None:
    descriptors = bd.load_board_descriptors()
    assert descriptors, "no packaged board descriptors found"

    missing_call: list[str] = []
    mismatches: list[str] = []
    for name, desc in sorted(descriptors.items()):
        soc_cmake = desc.path / "soc.cmake"
        assert soc_cmake.is_file(), f"{name}: missing soc.cmake at {soc_cmake}"
        args = _LOAD_SOC_FACTS_RE.findall(soc_cmake.read_text(encoding="utf-8"))
        if not args:
            missing_call.append(f"{name}: no nsx_load_soc_facts(\"…\") call in soc.cmake")
            continue
        for arg in args:
            if arg != desc.soc:
                mismatches.append(
                    f"{name}: board.yaml soc='{desc.soc}' but "
                    f"soc.cmake loads '{arg}'"
                )

    assert not missing_call, "boards missing the SoC-facts load call:\n" + "\n".join(
        missing_call
    )
    assert not mismatches, (
        "board.yaml soc drifted from soc.cmake nsx_load_soc_facts:\n"
        + "\n".join(mismatches)
    )
