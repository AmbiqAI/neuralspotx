#!/usr/bin/env python3
"""Generate the example target-support matrix in ``docs/examples/index.md``.

Single source of truth split:

* **Board matrix** is derived from each ``examples/<name>/nsx.yml``
  ``targets:`` block (``default`` + ``supported``) so it can never drift
  from what the app actually builds.
* **Human descriptors** (tier, capabilities, summary, status, tested
  boards) come from the YAML frontmatter on each ``docs/examples/<name>.md``
  page — mkdocs-native page metadata that renders cleanly.

The rendered Markdown table is spliced into ``docs/examples/index.md``
between the sentinel comments. Run manually after adding/retargeting an
example::

    python scripts/gen_examples_table.py

Drift is guarded by ``tests/test_examples_gallery_drift.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
DOCS_DIR = REPO_ROOT / "docs" / "examples"
INDEX = DOCS_DIR / "index.md"

BEGIN = "<!-- BEGIN GENERATED EXAMPLE MATRIX (scripts/gen_examples_table.py) -->"
END = "<!-- END GENERATED EXAMPLE MATRIX -->"

TIER_ORDER = {"basics": 0, "capabilities": 1, "integrations": 2}
REQUIRED_FRONTMATTER = ("tier", "capabilities", "summary", "status")
VALID_STATUS = {"tested", "builds", "experimental"}


class GalleryError(RuntimeError):
    """Raised when example metadata is missing or inconsistent."""


def example_dirs() -> list[Path]:
    return sorted(p.parent for p in EXAMPLES_DIR.glob("*/nsx.yml"))


def read_frontmatter(md_path: Path) -> dict:
    """Return the leading YAML frontmatter mapping of *md_path* (or ``{}``)."""

    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    block = text[4:end]
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def supported_boards(nsx_cfg: dict) -> tuple[str, list[str]]:
    """Return ``(default_board, supported_boards)`` from a ``targets:`` block."""

    targets = nsx_cfg.get("targets")
    if isinstance(targets, dict):
        supported = targets.get("supported", [])
        if isinstance(supported, dict):
            boards = list(supported)
        elif isinstance(supported, list):
            boards = [b for b in supported if isinstance(b, str)]
        else:
            boards = []
        default = targets.get("default")
        if not isinstance(default, str) or not default:
            default = boards[0] if boards else ""
        return default, boards
    # Legacy single-target fallback.
    target = nsx_cfg.get("target")
    board = target.get("board") if isinstance(target, dict) else None
    if isinstance(board, str) and board:
        return board, [board]
    return "", []


def collect_rows() -> list[dict]:
    rows: list[dict] = []
    for app_dir in example_dirs():
        name = app_dir.name
        nsx_cfg = yaml.safe_load((app_dir / "nsx.yml").read_text(encoding="utf-8")) or {}
        default, boards = supported_boards(nsx_cfg)

        doc_page = DOCS_DIR / f"{name}.md"
        if not doc_page.exists():
            raise GalleryError(
                f"examples/{name} has no docs page docs/examples/{name}.md. "
                "Add one (snippet include + frontmatter) so it appears in the gallery."
            )
        fm = read_frontmatter(doc_page)
        missing = [k for k in REQUIRED_FRONTMATTER if k not in fm]
        if missing:
            raise GalleryError(
                f"docs/examples/{name}.md frontmatter is missing required keys: {missing}"
            )
        status = str(fm["status"])
        if status not in VALID_STATUS:
            raise GalleryError(
                f"docs/examples/{name}.md status='{status}' invalid; "
                f"expected one of {sorted(VALID_STATUS)}"
            )
        tested = fm.get("boards_tested") or []
        if not isinstance(tested, list):
            raise GalleryError(f"docs/examples/{name}.md boards_tested must be a list")
        stray = [b for b in tested if b not in boards]
        if stray:
            raise GalleryError(
                f"docs/examples/{name}.md boards_tested {stray} not in "
                f"examples/{name}/nsx.yml targets.supported {boards}"
            )

        caps = fm["capabilities"]
        caps_list = caps if isinstance(caps, list) else [caps]
        rows.append({
            "name": name,
            "tier": str(fm["tier"]),
            "capabilities": [str(c) for c in caps_list],
            "summary": str(fm["summary"]).strip(),
            "status": status,
            "default": default,
            "boards": boards,
            "tested": [str(b) for b in tested],
        })

    rows.sort(key=lambda r: (TIER_ORDER.get(r["tier"], 99), r["name"]))
    return rows


def _fmt_boards(default: str, boards: list[str]) -> str:
    return ", ".join(f"**{b}**\u2009★" if b == default else b for b in boards)


def render_matrix(rows: list[dict] | None = None) -> str:
    rows = rows if rows is not None else collect_rows()
    lines = [
        BEGIN,
        "",
        "_Generated by `scripts/gen_examples_table.py` — do not edit by hand._",
        "_Boards come from each `nsx.yml` `targets.supported`; ★ marks the default._",
        "",
        "| Example | Tier | Capabilities | Supported boards | Tested on HW | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        example = f"[{r['name']}]({r['name']}.md)"
        caps = ", ".join(f"`{c}`" for c in r["capabilities"])
        boards = _fmt_boards(r["default"], r["boards"])
        tested = ", ".join(r["tested"]) if r["tested"] else "—"
        lines.append(
            f"| {example} | {r['tier']} | {caps} | {boards} | {tested} | {r['status']} |"
        )
    lines.extend(["", END])
    return "\n".join(lines)


def splice_index(matrix: str) -> str:
    text = INDEX.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise GalleryError(
            f"{INDEX.relative_to(REPO_ROOT)} is missing the sentinel markers "
            f"{BEGIN!r} / {END!r}. Add them where the matrix should render."
        )
    head = text[: text.index(BEGIN)]
    tail = text[text.index(END) + len(END) :]
    return head + matrix + tail


def main() -> int:
    rows = collect_rows()
    matrix = render_matrix(rows)
    new_index = splice_index(matrix)
    INDEX.write_text(new_index, encoding="utf-8", newline="\n")
    print(f"Wrote example matrix into {INDEX.relative_to(REPO_ROOT)} ({len(rows)} examples)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GalleryError as exc:  # pragma: no cover - CLI path
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
