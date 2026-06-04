"""Board descriptors — first-class, declarative board metadata.

Each packaged board under ``neuralspotx/boards/<name>/`` ships a
``board.yaml`` descriptor that is the **source of truth** for the
board's SoC, SoC family, SDK provider, CPU/ABI, and supported
toolchains. :mod:`neuralspotx.constants` derives its legacy
``DEFAULT_SOC_FOR_BOARD`` / ``BOARD_SDK_PROVIDER`` tables from these
descriptors instead of hand-maintained dicts.

This module deliberately imports only the standard library and PyYAML
so it can be imported by low-level modules (e.g. ``constants``) without
risking an import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# Directory holding the packaged board descriptors. Resolved relative to
# this module so it works for both editable and installed (non-zip) wheels.
BOARDS_DIR: Path = Path(__file__).resolve().parent / "boards"

# Current descriptor schema version. Bump when the on-disk shape changes.
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BoardCpu:
    """CPU / ABI facts for a board (mirrors ``board.cmake``)."""

    core: str
    float_abi: str
    abi: str


@dataclass(frozen=True)
class BoardDescriptor:
    """Declarative metadata for a single board.

    ``registered`` controls whether the board participates in the legacy
    ``constants.DEFAULT_SOC_FOR_BOARD`` / ``BOARD_SDK_PROVIDER`` tables.
    A board may ship a full package while remaining unregistered.
    """

    name: str
    tier: str
    soc: str
    soc_family: str
    sdk_provider: str
    registered: bool
    cpu: BoardCpu
    toolchains: tuple[str, ...]
    path: Path


class BoardDescriptorError(ValueError):
    """Raised when a ``board.yaml`` descriptor is malformed."""


def _require(mapping: dict, key: str, *, where: Path) -> object:
    if key not in mapping:
        raise BoardDescriptorError(f"{where}: missing required key '{key}'")
    return mapping[key]


def _parse_descriptor(path: Path) -> BoardDescriptor:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise BoardDescriptorError(f"{path}: top-level YAML must be a mapping")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise BoardDescriptorError(
            f"{path}: unsupported schema_version {version!r} "
            f"(expected {SCHEMA_VERSION})"
        )

    board = _require(raw, "board", where=path)
    if not isinstance(board, dict):
        raise BoardDescriptorError(f"{path}: 'board' must be a mapping")

    cpu = _require(raw, "cpu", where=path)
    if not isinstance(cpu, dict):
        raise BoardDescriptorError(f"{path}: 'cpu' must be a mapping")

    toolchains = raw.get("toolchains") or []
    if not isinstance(toolchains, list) or not all(
        isinstance(t, str) for t in toolchains
    ):
        raise BoardDescriptorError(f"{path}: 'toolchains' must be a list of strings")

    return BoardDescriptor(
        name=str(_require(board, "name", where=path)),
        tier=str(board.get("tier", "evb")),
        soc=str(_require(board, "soc", where=path)),
        soc_family=str(_require(raw, "soc_family", where=path)),
        sdk_provider=str(_require(raw, "sdk_provider", where=path)),
        registered=bool(board.get("registered", True)),
        cpu=BoardCpu(
            core=str(_require(cpu, "core", where=path)),
            float_abi=str(_require(cpu, "float_abi", where=path)),
            abi=str(_require(cpu, "abi", where=path)),
        ),
        toolchains=tuple(toolchains),
        path=path.parent,
    )


@lru_cache(maxsize=1)
def load_board_descriptors() -> dict[str, BoardDescriptor]:
    """Return all packaged board descriptors keyed by canonical board name.

    Results are sorted by board name and cached for the process lifetime.
    The descriptor ``name`` must match its directory name.
    """

    descriptors: dict[str, BoardDescriptor] = {}
    if not BOARDS_DIR.is_dir():
        return descriptors

    for board_yaml in sorted(BOARDS_DIR.glob("*/board.yaml")):
        descriptor = _parse_descriptor(board_yaml)
        dir_name = board_yaml.parent.name
        if descriptor.name != dir_name:
            raise BoardDescriptorError(
                f"{board_yaml}: board.name '{descriptor.name}' does not match "
                f"directory name '{dir_name}'"
            )
        descriptors[descriptor.name] = descriptor

    return descriptors


def load_board(name: str) -> BoardDescriptor | None:
    """Return the descriptor for *name*, or ``None`` if no board ships one."""

    return load_board_descriptors().get(name)


def list_boards(
    *, tier: str | None = None, registered_only: bool = False
) -> list[BoardDescriptor]:
    """Return descriptors, optionally filtered by ``tier`` / ``registered``."""

    boards = load_board_descriptors().values()
    result = [
        b
        for b in boards
        if (tier is None or b.tier == tier)
        and (not registered_only or b.registered)
    ]
    return result
