"""Board inspection and creation."""

from __future__ import annotations

from pathlib import Path
from typing import overload

from .. import operations
from .._errors import NSXConfigError
from .._io import Emitter, using_emitter
from ..board_descriptors import BoardDescriptor
from ._request_arguments import request_arguments
from ._requests import BoardCreateRequest

PathLike = str | Path


def describe_board(name: str, *, app_dir: PathLike | None = None) -> BoardDescriptor:
    """Return the effective descriptor, including inherited board facts.

    With an explicit app directory, look in its boards/ tree first and fall back
    to packaged descriptors. Omit app_dir to inspect the packaged catalog.
    Raises NSXConfigError for an unknown board, invalid descriptor or missing directory.
    """
    root = Path(app_dir).expanduser().resolve() if app_dir is not None else None
    return operations.describe_board_impl(name, app_dir=root)


@overload
def create_board(
    name: str,
    *,
    from_board: str,
    app_dir: PathLike = ".",
    force: bool = False,
    bsp_module: str | None = None,
    emit: Emitter | None = None,
) -> BoardDescriptor: ...


@overload
def create_board(
    name: BoardCreateRequest,
    *,
    from_board: str = ...,
    app_dir: PathLike = ".",
    force: bool = False,
    bsp_module: str | None = None,
    emit: Emitter | None = None,
) -> BoardDescriptor: ...


@request_arguments(BoardCreateRequest)
def create_board(
    name: str | BoardCreateRequest,
    *,
    from_board: str | None = None,
    app_dir: PathLike = ".",
    force: bool = False,
    bsp_module: str | None = None,
    emit: Emitter | None = None,
) -> BoardDescriptor:
    """Scaffold a custom board that inherits a registered EVB baseline.

    Args:
        name: Either the new board identifier or a typed request object.
        from_board: Parent EVB to inherit from (required unless ``name`` is a
            :class:`BoardCreateRequest`).
        app_dir: App root under which ``boards/<name>/`` is written.
        force: Overwrite an existing ``boards/<name>/`` directory.
        bsp_module: BSP provider module; defaults to nsx-bsp-<name>.
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
            bsp_module=bsp_module,
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
            bsp_module=request.bsp_module,
        )
