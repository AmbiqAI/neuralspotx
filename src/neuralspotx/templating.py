"""Helpers for rendering packaged NSX templates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


def render_template_tree(
    template_root: Path,
    destination_root: Path,
    *,
    context: dict[str, Any],
) -> None:
    """Render a packaged template tree into a destination directory.

    Args:
        template_root: Root directory containing source templates.
        destination_root: Destination directory to populate.
        context: Template variables available to ``*.j2`` files.
    """
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )

    for src in sorted(template_root.rglob("*")):
        rel = src.relative_to(template_root)
        if src.is_dir():
            (destination_root / rel).mkdir(parents=True, exist_ok=True)
            continue

        if src.suffix == ".j2":
            rendered_rel = rel.with_suffix("")
            target = destination_root / rendered_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            rendered = env.get_template(rel.as_posix()).render(**context)
            target.write_text(rendered, encoding="utf-8")
            continue

        target = destination_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
