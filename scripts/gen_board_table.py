#!/usr/bin/env python3
"""Generate ``nsx_board_table.cmake`` from ``constants.BOARDS``.

This script is the bridge that keeps the CMake registered-board
inventory in sync with the Python authoritative table in
:mod:`neuralspotx.constants`. The generated CMake file is consumed by
``nsx_sdk_providers.cmake``.

Run manually after editing ``BOARDS`` / packaged board descriptors::

    python scripts/gen_board_table.py

Drift between the Python board inventory and the committed file is guarded by
``tests/test_board_table_drift.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from neuralspotx.constants import BOARDS  # noqa: E402

OUTPUT = REPO_ROOT / "src" / "neuralspotx" / "cmake" / "nsx_board_table.cmake"


def render() -> str:
    lines = [
        "# Auto-generated from src/neuralspotx/constants.py BOARDS",
        "# by scripts/gen_board_table.py — DO NOT EDIT.",
        "#",
        "# Defines: nsx_board_is_registered(board_name out_var)",
        "#   Sets <out_var> in the parent scope to TRUE when the board name",
        "#   matches a registered packaged board, else FALSE.",
        "#   Board matching is case-insensitive.",
        "",
        "set(_NSX_REGISTERED_BOARDS_LOWER",
    ]

    for board in BOARDS:
        lines.append(f'    "{board.lower()}"')

    lines.extend([
        ")",
        "",
        "function(nsx_board_is_registered board_name out_var)",
        "    # Enable the IN_LIST if() operator (CMP0057). This file is also",
        "    # included in `cmake -P` script mode, where the policy otherwise",
        "    # defaults to OLD and IN_LIST raises an error.",
        "    if(POLICY CMP0057)",
        "        cmake_policy(SET CMP0057 NEW)",
        "    endif()",
        '    string(TOLOWER "${board_name}" _board_lc)',
        "    if(_board_lc IN_LIST _NSX_REGISTERED_BOARDS_LOWER)",
        '        set(${out_var} TRUE PARENT_SCOPE)',
        "    else()",
        '        set(${out_var} FALSE PARENT_SCOPE)',
        "    endif()",
        "endfunction()",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    content = render()
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(BOARDS)} boards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
