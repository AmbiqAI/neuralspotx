"""Drift guard for the generated example target-support matrix.

The matrix region in ``docs/examples/index.md`` must exactly match the
output of ``scripts/gen_examples_table.py``. Board columns derive from
each ``examples/<name>/nsx.yml`` ``targets:`` block; human descriptors
come from the frontmatter on each ``docs/examples/<name>.md`` page.

If this test fails, run::

    python scripts/gen_examples_table.py

and commit the regenerated ``docs/examples/index.md``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_SCRIPT = REPO_ROOT / "scripts" / "gen_examples_table.py"
INDEX = REPO_ROOT / "docs" / "examples" / "index.md"
EXAMPLES_DIR = REPO_ROOT / "examples"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_examples_table", GEN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_example_has_a_docs_page_with_frontmatter() -> None:
    """collect_rows() raises if any example lacks a page or required frontmatter."""

    gen = _load_generator()
    rows = gen.collect_rows()
    example_names = {p.parent.name for p in EXAMPLES_DIR.glob("*/nsx.yml")}
    assert {r["name"] for r in rows} == example_names


def test_tested_boards_are_a_subset_of_supported() -> None:
    gen = _load_generator()
    for row in gen.collect_rows():
        stray = [b for b in row["tested"] if b not in row["boards"]]
        assert not stray, f"{row['name']}: tested boards not in supported: {stray}"


def test_committed_matrix_matches_generator_output() -> None:
    """The matrix region in index.md must equal freshly rendered output."""

    gen = _load_generator()
    matrix = gen.render_matrix()
    actual = INDEX.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert gen.BEGIN in actual and gen.END in actual, (
        "docs/examples/index.md is missing the generated-matrix sentinels."
    )
    region = actual[actual.index(gen.BEGIN) : actual.index(gen.END) + len(gen.END)]
    assert region == matrix, (
        "Example matrix in docs/examples/index.md is stale. "
        "Run `python scripts/gen_examples_table.py` and commit the result."
    )
