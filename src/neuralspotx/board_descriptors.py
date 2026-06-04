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


def _apply_list_overrides(base: list[str], delta: object, *, where: Path) -> list[str]:
    """Apply a list override using ``+item`` / ``-item`` delta syntax.

    A list whose items are all plain (no ``+``/``-`` prefix) fully replaces
    *base*. A list mixing ``+item`` (add if absent) and ``-item`` (remove)
    entries is applied as an incremental delta against *base*. Mixing plain
    and prefixed items is rejected.
    """

    if not isinstance(delta, list) or not all(isinstance(x, str) for x in delta):
        raise BoardDescriptorError(f"{where}: override list must be a list of strings")

    prefixed = [x for x in delta if x[:1] in {"+", "-"}]
    if not prefixed:
        # Full replacement.
        return list(dict.fromkeys(delta))
    if len(prefixed) != len(delta):
        raise BoardDescriptorError(
            f"{where}: cannot mix plain and +/- prefixed items in an override list"
        )

    result = list(base)
    for item in delta:
        op, name = item[0], item[1:]
        if op == "+":
            if name not in result:
                result.append(name)
        else:  # op == "-"
            result = [x for x in result if x != name]
    return result


def _merge_inherited(
    raw: dict,
    parent: "BoardDescriptor",
    *,
    where: Path,
) -> dict:
    """Return a descriptor mapping with *parent* defaults folded into *raw*.

    Scalar fields declared on *raw* win over the parent. The optional
    ``overrides`` block applies ``+``/``-`` deltas to inherited list fields
    (currently ``toolchains``).
    """

    board = dict(raw.get("board") or {})
    merged: dict = {
        "schema_version": raw.get("schema_version", SCHEMA_VERSION),
        "soc_family": raw.get("soc_family", parent.soc_family),
        "sdk_provider": raw.get("sdk_provider", parent.sdk_provider),
        "cpu": raw.get("cpu")
        or {
            "core": parent.cpu.core,
            "float_abi": parent.cpu.float_abi,
            "abi": parent.cpu.abi,
        },
        "board": {
            "name": board.get("name"),
            "tier": board.get("tier", "custom"),
            "soc": board.get("soc", parent.soc),
            "registered": board.get("registered", False),
        },
    }

    toolchains = list(parent.toolchains)
    overrides = raw.get("overrides") or {}
    if not isinstance(overrides, dict):
        raise BoardDescriptorError(f"{where}: 'overrides' must be a mapping")
    if "toolchains" in overrides:
        toolchains = _apply_list_overrides(
            toolchains, overrides["toolchains"], where=where
        )
    elif "toolchains" in raw:
        toolchains = raw["toolchains"]
    merged["toolchains"] = toolchains
    return merged


def _build_descriptor(raw: dict, *, path: Path) -> BoardDescriptor:
    """Construct a :class:`BoardDescriptor` from a fully-resolved mapping."""

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


def _parse_descriptor(
    path: Path,
    *,
    parent_lookup: "dict[str, BoardDescriptor] | None" = None,
) -> BoardDescriptor:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise BoardDescriptorError(f"{path}: top-level YAML must be a mapping")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise BoardDescriptorError(
            f"{path}: unsupported schema_version {version!r} "
            f"(expected {SCHEMA_VERSION})"
        )

    inherits = raw.get("inherits")
    if inherits is not None:
        lookup = parent_lookup if parent_lookup is not None else load_board_descriptors()
        parent = lookup.get(str(inherits))
        if parent is None:
            raise BoardDescriptorError(
                f"{path}: inherits unknown board '{inherits}' "
                f"(known: {sorted(lookup)})"
            )
        resolved = _merge_inherited(raw, parent, where=path)
        return _build_descriptor(resolved, path=path)

    return _build_descriptor(raw, path=path)


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


def load_board_descriptor_file(
    path: Path,
    *,
    parent_lookup: dict[str, BoardDescriptor] | None = None,
) -> BoardDescriptor:
    """Load a single ``board.yaml`` file, resolving ``inherits`` if present.

    Used for app-local *custom* boards that live outside the packaged
    ``boards/`` tree. ``inherits`` resolves against the packaged board
    descriptors by default, so a custom board can declare only the fields
    that differ from its EVB baseline.
    """

    return _parse_descriptor(path, parent_lookup=parent_lookup)


def render_custom_board_yaml(
    *,
    name: str,
    parent: str,
    tier: str = "custom",
) -> str:
    """Render a minimal custom ``board.yaml`` that inherits from *parent*.

    The result declares only the board identity and the inheritance link;
    all SoC/provider/CPU/toolchain facts are inherited from *parent* at
    load time. Callers may hand-edit the file to add an ``overrides`` block.
    """

    return (
        "# NSX custom board descriptor (schema_version 1).\n"
        f"# Inherits all SoC/provider/CPU/toolchain facts from '{parent}'.\n"
        "# Add an 'overrides:' block to tweak inherited lists, e.g.\n"
        "#   overrides:\n"
        "#     toolchains: [-armclang]   # drop a toolchain\n"
        "schema_version: 1\n"
        f"inherits: {parent}\n"
        "board:\n"
        f"  name: {name}\n"
        f"  tier: {tier}\n"
        "  registered: false\n"
    )


def render_custom_board_cmake(*, name: str, parent: str) -> str:
    """Render a thin ``board.cmake`` that delegates to the *parent* EVB.

    The custom board reuses the parent's startup/linker/flag wiring and
    only re-aliases the board target under its own name, so a custom board
    on an existing SoC needs no hand-written CMake by default.
    """

    return (
        "# Auto-generated thin board.cmake for a custom board.\n"
        f"# Delegates all SoC/startup/linker wiring to parent EVB '{parent}'.\n"
        f'set(NSX_PARENT_BOARD "{parent}")\n'
        'include("${NSX_ROOT}/boards/${NSX_PARENT_BOARD}/board.cmake")\n'
        "\n"
        "# Re-export the parent board target under this custom board's name so\n"
        "# top-level CMakeLists can link nsx::board_<custom> if desired.\n"
        f"if(NOT TARGET nsx::board_{name})\n"
        f"    add_library(nsx::board_{name} ALIAS ${{NSX_BOARD_TARGET}})\n"
        "endif()\n"
    )
