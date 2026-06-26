"""Board scaffolding operations (``create_board_impl``)."""

from __future__ import annotations

from pathlib import Path

from .. import board_descriptors as bd
from .._errors import NSXConfigError
from .._io import info
from ..project_config import resolve_app_dir

PathLike = str | Path


def create_board_impl(
    name: str,
    *,
    from_board: str,
    app_dir: PathLike | None = None,
    force: bool = False,
) -> bd.BoardDescriptor:
    """Scaffold a custom board that inherits an EVB baseline.

    Writes ``boards/<name>/{board.yaml,board.cmake}`` under the resolved app
    directory and returns the freshly parsed descriptor — which also validates
    that the generated ``inherits`` link resolves against its parent.

    Raises ``NSXConfigError`` if the parent board is unknown or the target
    directory already exists without ``force``.
    """

    parent = bd.load_board(from_board)
    if parent is None:
        raise NSXConfigError(
            f"unknown parent board '{from_board}' "
            f"(run `nsx board list` to see available boards)"
        )

    root = resolve_app_dir(app_dir)
    board_dir = root / "boards" / name
    if board_dir.exists() and not force:
        raise NSXConfigError(
            f"board directory already exists: {board_dir} (use --force to overwrite)"
        )
    board_dir.mkdir(parents=True, exist_ok=True)

    (board_dir / "board.yaml").write_text(
        bd.render_custom_board_yaml(name=name, parent=parent.name), encoding="utf-8"
    )
    (board_dir / "board.cmake").write_text(
        bd.render_custom_board_cmake(name=name, parent=parent.name), encoding="utf-8"
    )

    # Validate the generated descriptor resolves against its parent.
    resolved = bd.load_board_descriptor_file(board_dir / "board.yaml")

    info(f"Created custom board '{name}' (inherits {parent.name}) at:")
    info(f"  {board_dir}")
    info("Next steps:")
    info(f"  1) Edit boards/{name}/board.yaml to add an 'overrides:' block if needed")
    info(f"  2) Set target.board: {name} in nsx.yml")
    info("  3) Run `nsx lock` then `nsx configure`")
    return resolved
