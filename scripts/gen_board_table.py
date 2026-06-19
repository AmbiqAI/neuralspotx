#!/usr/bin/env python3
"""Generate ``nsx_board_table.cmake`` from ``constants.BOARD_SDK_PROVIDER``.

This script is the bridge that keeps the CMake board → SDK provider
mapping in sync with the Python authoritative table in
:mod:`neuralspotx.constants`. The generated CMake file is consumed by
``nsx_sdk_providers.cmake``.

Run manually after editing ``BOARD_SDK_PROVIDER``::

    python scripts/gen_board_table.py

Drift between the dict and the committed file is guarded by
``tests/test_board_table_drift.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from neuralspotx.constants import BOARD_SDK_PROVIDER  # noqa: E402

OUTPUT = REPO_ROOT / "src" / "neuralspotx" / "cmake" / "nsx_board_table.cmake"


def render() -> str:
    lines = [
        "# Auto-generated from src/neuralspotx/constants.py BOARD_SDK_PROVIDER",
        "# by scripts/gen_board_table.py — DO NOT EDIT.",
        "#",
        "# Defines: nsx_lookup_sdk_provider(board_name out_var)",
        "#   Sets <out_var> in the parent scope to the canonical SDK",
        "#   provider name (ambiqsuite)",
        "#   for the given board, or to the empty string if unknown.",
        "#   Board matching is case-insensitive.",
        "",
        "function(nsx_lookup_sdk_provider board_name out_var)",
        '    string(TOLOWER "${board_name}" _board_lc)',
    ]

    branch_keyword = "if"
    for board, provider in BOARD_SDK_PROVIDER.items():
        lines.append(f'    {branch_keyword}(_board_lc STREQUAL "{board.lower()}")')
        lines.append(
            f'        set({{out_var}} "{provider}" PARENT_SCOPE)'.replace("{out_var}", "${out_var}")
        )
        branch_keyword = "elseif"

    lines.extend([
        "    else()",
        '        set(${out_var} "" PARENT_SCOPE)',
        "    endif()",
        "endfunction()",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    content = render()
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(BOARD_SDK_PROVIDER)} boards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
