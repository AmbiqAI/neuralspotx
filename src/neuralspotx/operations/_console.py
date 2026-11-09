"""Shared advisory transport diagnostics for SWO and RTT callers."""

from pathlib import Path
from typing import Literal

from .._io import warn
from ..project_config import load_project_config


def warn_console_mismatch(
    app: Path, board: str, requested: Literal["swo", "rtt"], *, target: str | None = None
) -> None:
    config = load_project_config(app / "nsx.yml").app_config()
    if target is not None and target != config.project_name:
        return
    declared = config.console_for_board(board)
    if declared is None or declared.transport == requested:
        return
    command = "nsx rtt" if declared.transport == "rtt" else "nsx view"
    warn(
        f"Primary console for {board} is declared {declared.transport.upper()}, but "
        f"{requested.upper()} was requested. Consider {command} for this app and board; "
        "continuing with the requested transport. SWO view retains its documented reset policy.",
        code="console_transport_mismatch",
        declared_transport=declared.transport,
        requested_transport=requested,
        board=board,
        suggested_command=command,
    )
