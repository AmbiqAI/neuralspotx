"""Board descriptors — first-class, declarative board metadata.

Each packaged board under ``neuralspotx/boards/<name>/`` ships a
``board.yaml`` descriptor that is the **source of truth** for the
board's SoC, SDK provider, CPU/ABI, and supported toolchains.
:mod:`neuralspotx.constants` derives its legacy
``DEFAULT_SOC_FOR_BOARD`` / ``BOARD_SDK_PROVIDER`` tables from these
descriptors instead of hand-maintained dicts.

This module deliberately imports only the standard library and PyYAML
so it can be imported by low-level modules (e.g. ``constants``) without
risking an import cycle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .bsp_contracts import BspBinding, identifier

# Directory holding the packaged board descriptors. Resolved relative to
# this module so it works for both editable and installed (non-zip) wheels.
BOARDS_DIR: Path = Path(__file__).resolve().parent / "boards"

# Current descriptor schema version. Bump when the on-disk shape changes.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class BoardCpu:
    """CPU / ABI facts for a board.

    These mirror the build-time single source of truth in the
    ``nsx-ambiq-sdk`` module (``cmake/socs/facts/<soc>.cmake``:
    ``NSX_CPU`` / ``NSX_FLOAT_ABI`` / ``NSX_ABI_FLAGS``). This descriptor
    copy is used for ``nsx board info`` display; the cross-repo
    ``tests/test_board_cpu_facts_contract.py`` guards the two from drifting.
    """

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
    sdk_provider: str
    registered: bool
    cpu: BoardCpu
    toolchains: tuple[str, ...]
    path: Path
    bsp: BspBinding = BspBinding("nsx-ambiq-bsp", 1)
    revision: str | None = None
    descriptor_inputs: tuple[Path, ...] = ()


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
        "sdk_provider": raw.get("sdk_provider", parent.sdk_provider),
        "roles": raw.get("roles"),
        "cpu": raw.get("cpu")
        or {
            "core": parent.cpu.core,
            "float_abi": parent.cpu.float_abi,
            "abi": parent.cpu.abi,
        },
        "board": {
            "name": board.get("name"),
            "revision": board.get("revision"),
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
        toolchains = _apply_list_overrides(toolchains, overrides["toolchains"], where=where)
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
    if not isinstance(toolchains, list) or not all(isinstance(t, str) for t in toolchains):
        raise BoardDescriptorError(f"{path}: 'toolchains' must be a list of strings")

    roles = raw.get("roles")
    if not isinstance(roles, dict) or set(roles) != {"bsp"}:
        raise BoardDescriptorError(
            f"{path}: roles must declare exactly bsp; author an explicit provider binding"
        )
    try:
        binding = BspBinding.parse(roles["bsp"], f"{path}: roles.bsp")
        identifier(board.get("name"), f"{path}: board.name")
    except ValueError as exc:
        raise BoardDescriptorError(str(exc)) from exc
    revision = board.get("revision")
    if revision is not None and (not isinstance(revision, str) or not revision.strip()):
        raise BoardDescriptorError(f"{path}: board.revision must be a nonempty string")
    return BoardDescriptor(
        bsp=binding,
        revision=revision,
        descriptor_inputs=(path,),
        name=str(_require(board, "name", where=path)),
        tier=str(board.get("tier", "evb")),
        soc=str(_require(board, "soc", where=path)),
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
    parent_resolver: Callable[[str], BoardDescriptor | None] | None = None,
) -> BoardDescriptor:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BoardDescriptorError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise BoardDescriptorError(f"{path}: top-level YAML must be a mapping")

    version = raw.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        raise BoardDescriptorError(
            f"{path}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION}); "
            "update board.yaml to schema 2 with an explicit roles.bsp binding"
        )

    inherits = raw.get("inherits")
    if inherits is not None:
        lookup = parent_lookup if parent_lookup is not None else load_board_descriptors()
        parent = parent_resolver(str(inherits)) if parent_resolver else lookup.get(str(inherits))
        if parent is None:
            raise BoardDescriptorError(
                f"{path}: inherits unknown board '{inherits}' (known: {sorted(lookup)})"
            )
        resolved = _merge_inherited(raw, parent, where=path)
        from dataclasses import replace

        descriptor = _build_descriptor(resolved, path=path)
        return replace(descriptor, descriptor_inputs=(*parent.descriptor_inputs, path))

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


def list_boards(*, tier: str | None = None, registered_only: bool = False) -> list[BoardDescriptor]:
    """Return descriptors, optionally filtered by ``tier`` / ``registered``."""

    boards = load_board_descriptors().values()
    result = [
        b
        for b in boards
        if (tier is None or b.tier == tier) and (not registered_only or b.registered)
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


def load_board_for_app(name: str, app_dir: Path | None = None) -> BoardDescriptor | None:
    """Read the app-local board snapshot, including its inherited inputs, first."""
    active: set[str] = set()

    def resolve(board: str) -> BoardDescriptor | None:
        try:
            identifier(board, "board identity")
        except ValueError as exc:
            raise BoardDescriptorError(str(exc)) from exc
        if board in active or len(active) >= 32:
            raise BoardDescriptorError(f"Board inheritance cycle or excessive depth at '{board}'")
        path = app_dir / "boards" / board / "board.yaml" if app_dir else None
        if path is None or not path.is_file():
            path = BOARDS_DIR / board / "board.yaml"
        if not path.is_file():
            return None
        active.add(board)
        try:
            result = _parse_descriptor(path, parent_lookup={}, parent_resolver=resolve)
            if result.name != board:
                raise BoardDescriptorError(f"{path}: descriptor identity must equal '{board}'")
            return result
        finally:
            active.remove(board)

    return resolve(name)


def _render_board_fragment(fragment: str, **context: str) -> str:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates" / "custom-board")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return env.get_template(fragment + ".j2").render(**context)


def render_custom_board_yaml(*, name: str, parent: str, tier: str = "custom") -> str:
    """Render the board descriptor with an explicit custom BSP binding."""
    identifier(name, "board name")
    identifier(parent, "parent board")
    return _render_board_fragment(
        "board.yaml",
        name=name,
        parent=parent,
        tier=tier,
        bsp_module="nsx-bsp-" + name.replace("_", "-").lower(),
    )


def render_custom_board_cmake(*, name: str, parent: str) -> str:
    """Render independent silicon bootstrap, without parent EVB wiring."""
    identifier(name, "board name")
    return _render_board_fragment("board.cmake", name=name)
