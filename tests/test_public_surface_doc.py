"""Keep ``neuralspotx.__all__`` and ``docs/reference/public-api.md`` in sync.

The doc lists every public name in a markdown table column. We extract
those names with a simple regex and assert the set matches ``__all__``.
"""

from __future__ import annotations

import re
from pathlib import Path

import neuralspotx

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "reference" / "public-api.md"


def _extract_doc_symbols() -> set[str]:
    """Pull every backticked identifier from the first column of any
    markdown table in ``public-api.md``.

    A table row looks like ``| `Name` | ... | ... |``. Some cells list
    multiple names separated by commas (``| `A`, `B` |``); we accept
    those too.
    """

    text = DOC_PATH.read_text(encoding="utf-8")
    symbols: set[str] = set()
    row_re = re.compile(r"^\|\s*([^|]+?)\s*\|")
    ident_re = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
    for line in text.splitlines():
        m = row_re.match(line)
        if not m:
            continue
        first_col = m.group(1)
        # Skip header / separator rows.
        if first_col.strip().lower() in {"symbol", ""} or set(first_col.strip()) <= {"-", ":"}:
            continue
        for ident in ident_re.findall(first_col):
            symbols.add(ident)
    return symbols


def test_public_api_doc_matches_all() -> None:
    declared = set(neuralspotx.__all__)
    documented = _extract_doc_symbols()
    missing_from_doc = declared - documented
    extra_in_doc = documented - declared
    assert not missing_from_doc, (
        f"Names in neuralspotx.__all__ but not documented in {DOC_PATH.name}: "
        f"{sorted(missing_from_doc)}"
    )
    assert not extra_in_doc, (
        f"Names documented in {DOC_PATH.name} but missing from neuralspotx.__all__: "
        f"{sorted(extra_in_doc)}"
    )


def test_every_public_name_is_importable() -> None:
    for name in neuralspotx.__all__:
        assert hasattr(neuralspotx, name), (
            f"neuralspotx.__all__ lists {name!r} but it is not importable"
        )
