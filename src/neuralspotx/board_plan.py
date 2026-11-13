"""One board selection shared by dependency planning and CMake generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._errors import NSXConfigError
from .board_descriptors import BoardDescriptor, BoardDescriptorError, load_board_for_app
from .constants import normalize_board, normalize_soc


@dataclass(frozen=True)
class ResolvedBoardPlan:
    descriptor: BoardDescriptor

    @property
    def board_module(self) -> str:
        return "nsx-board-" + self.descriptor.name.replace("_", "-").lower()


def resolve_board_plan(app_dir: Path | None, config: dict[str, Any]) -> ResolvedBoardPlan | None:
    target = config.get("target") or {}
    board = target.get("board")
    if not isinstance(board, str) or not board:
        return None
    try:
        descriptor = load_board_for_app(normalize_board(board), app_dir)
    except BoardDescriptorError as exc:
        raise NSXConfigError(str(exc)) from exc
    if descriptor is None:
        if config.get("baseline") == "none":
            return None
        raise NSXConfigError(
            f"Board '{board}' has no board.yaml; create/register the board before resolving modules"
        )
    soc = normalize_soc(target.get("soc"))
    if soc and soc != descriptor.soc:
        raise NSXConfigError(
            f"Target SoC '{soc}' disagrees with board '{board}' ({descriptor.soc})"
        )
    return ResolvedBoardPlan(descriptor)
