"""Board scaffolding operations (``create_board_impl``)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import board_descriptors as bd
from .._errors import NSXConfigError
from .._io import info
from ..bsp_contracts import identifier
from ..project_config import resolve_app_dir
from ..templating import render_template_tree

PathLike = str | Path


def create_board_impl(
    name: str,
    *,
    from_board: str,
    app_dir: PathLike | None = None,
    force: bool = False,
    bsp_module: str | None = None,
) -> bd.BoardDescriptor:
    """Scaffold a custom board that inherits an EVB baseline.

    Writes ``boards/<name>/{board.yaml,board.cmake}`` under the resolved app
    directory and returns the freshly parsed descriptor — which also validates
    that the generated ``inherits`` link resolves against its parent.

    Raises ``NSXConfigError`` if the parent board is unknown or the target
    directory already exists without ``force``.
    """

    try:
        identifier(name, "board name")
        bsp_module = identifier(
            bsp_module or "nsx-bsp-" + name.replace("_", "-").lower(), "BSP module"
        )
    except ValueError as exc:
        raise NSXConfigError(str(exc)) from exc
    if name == from_board:
        raise NSXConfigError("Custom board identity must differ from its inherited board")
    root = resolve_app_dir(app_dir)
    parent = bd.load_board_for_app(from_board, root)
    if parent is None:
        raise NSXConfigError(
            f"unknown parent board '{from_board}' (run `nsx board list` to see available boards)"
        )

    root = resolve_app_dir(app_dir)
    board_dir = root / "boards" / name
    if board_dir.exists() and not force:
        raise NSXConfigError(
            f"board directory already exists: {board_dir} (use --force to overwrite)"
        )
    board_dir.mkdir(parents=True, exist_ok=True)

    for source in parent.descriptor_inputs:
        snapshot = root / "boards" / source.parent.name / "board.yaml"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != snapshot.resolve():
            shutil.copy2(source, snapshot)
    render_template_tree(
        Path(__file__).resolve().parents[1] / "templates" / "custom-board",
        board_dir,
        context={
            "name": name,
            "parent": parent.name,
            "soc": parent.soc,
            "bsp_module": bsp_module,
            "toolchains": list(parent.toolchains),
            "board_module": "nsx-board-" + name.replace("_", "-").lower(),
        },
    )
    resolved = bd.load_board_for_app(name, root)
    assert resolved is not None

    info(f"Created custom board '{name}' (inherits {parent.name}) at:")
    info(f"  {board_dir}")
    info("Next steps:")
    info(f"  1) Edit boards/{name}/board.yaml to add an 'overrides:' block if needed")
    info(f"  2) Set target.board: {name} in nsx.yml")
    info(f"  3) Register BSP module {bsp_module} offering contract 2 for {parent.soc}")
    info("  4) Run `nsx lock` then `nsx configure`")
    return resolved
