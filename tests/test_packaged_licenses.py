"""License contract for board and tooling content vendored into NSX apps."""

from __future__ import annotations

from pathlib import Path

import neuralspotx

PACKAGE_DIR = Path(neuralspotx.__file__).resolve().parent
LICENSE_TEXT = (PACKAGE_DIR.parent.parent / "LICENSE").read_text(encoding="utf-8")
SPDX_HEADER = "SPDX-License-Identifier: BSD-3-Clause"
COPYRIGHT_HEADER = "Copyright (c) 2026, Ambiq"
SOURCE_SUFFIXES = {".cmake", ".in", ".yaml"}


def _packaged_roots() -> list[Path]:
    board_roots = sorted(
        path
        for path in (PACKAGE_DIR / "boards").iterdir()
        if path.is_dir() and (path / "nsx-module.yaml").is_file()
    )
    return [*board_roots, PACKAGE_DIR / "cmake"]


def test_packaged_modules_carry_the_project_license() -> None:
    for root in _packaged_roots():
        assert (root / "LICENSE").read_text(encoding="utf-8") == LICENSE_TEXT


def test_packaged_module_sources_carry_spdx_headers() -> None:
    missing: list[str] = []
    for root in _packaged_roots():
        sources = sorted(path for path in root.rglob("*") if path.suffix in SOURCE_SUFFIXES)
        for source in sources:
            text = source.read_text(encoding="utf-8")
            if SPDX_HEADER not in text or COPYRIGHT_HEADER not in text:
                missing.append(source.relative_to(PACKAGE_DIR).as_posix())

    assert not missing, "Packaged sources missing BSD-3-Clause headers:\n  " + "\n  ".join(missing)
