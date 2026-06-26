"""Board-scoped programmatic API: ``create_board``."""

from __future__ import annotations

from pathlib import Path

from .. import operations
from .._errors import NSXConfigError
from .._io import Emitter, using_emitter
from ..board_descriptors import BoardDescriptor
from ._requests import BoardCreateRequest

PathLike = str | Path


def create_board(
    name: str | BoardCreateRequest,
    *,
    from_board: str | None = None,
    app_dir: PathLike = ".",
    force: bool = False,
    emit: Emitter | None = None,
) -> BoardDescriptor:
    """Scaffold a custom board that inherits a registered EVB baseline.

    Args:
        name: Either the new board identifier or a typed request object.
        from_board: Parent EVB to inherit from (required unless ``name`` is a
            :class:`BoardCreateRequest`).
        app_dir: App root under which ``boards/<name>/`` is written.
        force: Overwrite an existing ``boards/<name>/`` directory.
        emit: Optional event sink for progress/next-step messages.

    Returns:
        The freshly parsed :class:`BoardDescriptor` for the new board.
    """

    request = (
        name
        if isinstance(name, BoardCreateRequest)
        else BoardCreateRequest(
            name=name,
            from_board=from_board or "",
            app_dir=app_dir,
            force=force,
        )
    )
    if not request.from_board:
        raise NSXConfigError("create_board requires a parent board via 'from_board'")
    with using_emitter(emit):
        return operations.create_board_impl(
            request.name,
            from_board=request.from_board,
            app_dir=request.app_dir,
            force=request.force,
        )
