"""Typed ``nsx.yml`` loader (Phase 3 — formats freeze)."""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .._errors import NSXConfigError
from ._project import AppConfig, AppModule, ModuleRegistryOverride

# ------------------------------------------------------------------
# Typed nsx.yml loader (Phase 3 — formats freeze)
# ------------------------------------------------------------------


_NSX_YML_KNOWN_TOP_LEVEL: tuple[str, ...] = (
    "schema_version",
    "project",
    "target",
    "toolchain",
    "channel",
    "modules",
    "module_registry",
    "tooling",
    "features",
    "profile",
    "profile_status",
    "targets",
    "baseline",
)

# The single nsx.yml schema version this build understands. Bumped to 2 for
# the unified dependency model (one ``modules:`` list carrying per-entry
# ``source`` + ``boards``; the old ``requires:`` field and authoritative-only
# ``modules:`` semantics were removed — a deliberate pre-1.0 breaking change).
SUPPORTED_SCHEMA_VERSION = 2


def _require_mapping(
    value: Any, *, field: str, allow_none: bool = False, origin: str = "nsx.yml"
) -> dict[str, Any]:
    """Validate that *value* is a mapping; raise :class:`NSXConfigError`.

    When *allow_none* is True, ``None`` is accepted and an empty dict
    is returned. The *field* argument names the offending YAML key
    path so the resulting error carries it on ``.field``. *origin*
    prefixes the error message with the source location (defaults to
    the literal ``"nsx.yml"`` for callers that have no real path).
    """

    if value is None and allow_none:
        return {}
    if not isinstance(value, dict):
        raise NSXConfigError(
            f"{origin}: '{field}' must be a mapping, got {type(value).__name__}",
            field=field,
        )
    return value


def _require_str(
    value: Any, *, field: str, allow_empty: bool = False, origin: str = "nsx.yml"
) -> str:
    if not isinstance(value, str):
        raise NSXConfigError(
            f"{origin}: '{field}' must be a string, got {type(value).__name__}",
            field=field,
        )
    if not value and not allow_empty:
        raise NSXConfigError(f"{origin}: '{field}' must be a non-empty string", field=field)
    return value


def _reject_requires(value: Any, *, field: str, origin: str = "nsx.yml") -> None:
    """Reject the removed ``requires:`` field with a migration hint.

    Schema v2 unifies dependencies under a single ``modules:`` list, where each
    entry carries an optional per-entry ``boards:`` filter and ``source:``. The
    old additive ``requires:`` field (top-level or per-target) is gone.
    """

    if value is None:
        return
    raise NSXConfigError(
        f"{origin}: '{field}' is no longer supported (schema v2). List dependencies "
        "under 'modules:' instead — each entry is a name with an optional 'boards:' "
        "filter and 'source:' (path / vendored / git).",
        field=field,
    )


def _validate_baseline(value: Any, *, origin: str = "nsx.yml") -> None:
    """Validate the optional ``baseline:`` opt-out.

    The only accepted value is the string ``"none"``, which disables board
    profile seeding so the ``modules:`` list is the authoritative closure.
    Absence (the default) means the board profile baseline is layered in.
    """

    if value is None:
        return
    if value != "none":
        raise NSXConfigError(
            f"{origin}: 'baseline' only supports the value 'none' (got {value!r})",
            field="baseline",
        )


def _validate_module_sources(
    modules: tuple[AppModule, ...], *, origin: str = "nsx.yml"
) -> None:
    """Validate each ``modules[i].source`` declares at most one source kind.

    A dependency's source is exactly one of ``path`` / ``vendored`` / ``git``
    (or none, meaning registry-resolved). ``rev`` only makes sense with
    ``git``. Conflicting combinations fail fast with the offending field path.
    """

    for idx, module in enumerate(modules):
        src = module.source
        declared = [
            name
            for name, present in (
                ("path", src.path is not None),
                ("vendored", src.vendored),
                ("git", src.git is not None),
            )
            if present
        ]
        if len(declared) > 1:
            raise NSXConfigError(
                f"{origin}: modules[{idx}] ('{module.name}') source declares multiple "
                f"kinds ({', '.join(declared)}); choose exactly one of path / vendored / git",
                field=f"modules[{idx}].source",
            )
        if src.rev is not None and src.git is None:
            raise NSXConfigError(
                f"{origin}: modules[{idx}] ('{module.name}') source 'rev' requires 'git'",
                field=f"modules[{idx}].source.rev",
            )


def _declared_board_names(data: dict[str, Any]) -> set[str]:
    """Collect every board declared by the manifest's target(s).

    Unions the multi-target ``targets.supported`` board names (list entries or
    mapping keys) with the legacy singular ``target.board``. Used to validate
    per-entry ``modules[i].boards`` filters against real targets.
    """

    names: set[str] = set()
    targets = data.get("targets")
    if isinstance(targets, dict):
        supported = targets.get("supported")
        if isinstance(supported, list):
            names.update(b for b in supported if isinstance(b, str) and b)
        elif isinstance(supported, dict):
            names.update(b for b in supported if isinstance(b, str) and b)
    target = data.get("target")
    if isinstance(target, dict):
        board = target.get("board")
        if isinstance(board, str) and board:
            names.add(board)
    return names


def _validate_module_boards_subset(
    data: dict[str, Any], modules: tuple[AppModule, ...], *, origin: str = "nsx.yml"
) -> None:
    """Ensure each ``modules[i].boards`` filter references a declared target.

    A per-entry ``boards`` list scopes a dependency to specific boards; every
    listed board must be a declared target (``targets.supported`` or the legacy
    ``target.board``) so a typo fails fast instead of silently never applying.
    Skipped when the manifest declares no targets at all.
    """

    declared = _declared_board_names(data)
    if not declared:
        return
    for idx, module in enumerate(modules):
        unknown = [b for b in module.boards if b not in declared]
        if unknown:
            listed = ", ".join(sorted(declared))
            raise NSXConfigError(
                f"{origin}: modules[{idx}] ('{module.name}') boards "
                f"{unknown} are not declared targets (supported: {listed})",
                field=f"modules[{idx}].boards",
            )


def _validate_targets(value: Any, *, origin: str = "nsx.yml") -> None:
    """Validate the optional multi-target ``targets:`` block shape.

    The block carries an optional ``default`` board name and a ``supported``
    list of board names (or a mapping of board name to an optional
    ``{soc, profile, toolchain}`` override). Resolution semantics live in
    :meth:`AppConfig.targets`; this only enforces structural shape so a typo
    fails fast with a typed, field-scoped error.
    """

    if value is None:
        return
    block = _require_mapping(value, field="targets", origin=origin)
    default = block.get("default")
    if default is not None:
        _require_str(default, field="targets.default", origin=origin)
    supported = block.get("supported")
    if supported is None:
        return
    if isinstance(supported, list):
        for idx, item in enumerate(supported):
            _require_str(item, field=f"targets.supported[{idx}]", origin=origin)
        supported_names = [s for s in supported if isinstance(s, str)]
    elif isinstance(supported, dict):
        for board, cfg in supported.items():
            _require_str(board, field="targets.supported (board key)", origin=origin)
            if cfg is None:
                continue
            cfg_map = _require_mapping(cfg, field=f"targets.supported.{board}", origin=origin)
            for key in ("soc", "profile", "toolchain"):
                if cfg_map.get(key) is not None:
                    _require_str(
                        cfg_map[key], field=f"targets.supported.{board}.{key}", origin=origin
                    )
            _reject_requires(
                cfg_map.get("requires"),
                field=f"targets.supported.{board}.requires",
                origin=origin,
            )
        supported_names = [b for b in supported if isinstance(b, str)]
    else:
        raise NSXConfigError(
            f"{origin}: 'targets.supported' must be a list or a mapping, "
            f"got {type(supported).__name__}",
            field="targets.supported",
        )

    if isinstance(default, str) and default and default not in supported_names:
        listed = ", ".join(supported_names) or "(none)"
        raise NSXConfigError(
            f"{origin}: 'targets.default' ({default!r}) must be one of "
            f"targets.supported ({listed})",
            field="targets.default",
        )


def _validate_modules_list(modules_data: Any, *, origin: str = "nsx.yml") -> tuple[AppModule, ...]:
    """Validate the top-level ``modules`` list and return typed entries.

    Each list element must be a mapping; the per-element validation is
    delegated to :meth:`AppModule.from_mapping`, which raises a typed
    :class:`NSXConfigError` with ``.field`` already set to the
    ``modules[i]`` / ``modules[i].<key>`` path.  Nested field paths are
    preserved as-is; only top-level shape errors fall back to a bare
    ``modules[i]`` field tag.
    """

    if modules_data is None:
        return ()
    if not isinstance(modules_data, list):
        raise NSXConfigError(
            f"{origin}: 'modules' must be a list, got {type(modules_data).__name__}",
            field="modules",
        )
    out: list[AppModule] = []
    for idx, item in enumerate(modules_data):
        try:
            out.append(AppModule.from_mapping(idx, item, origin=origin))
        except NSXConfigError as exc:
            # AppModule.from_mapping sets exc.field to the structured
            # path (e.g. ``modules[0].name``). Preserve it verbatim so
            # callers see the deepest offending key, not just the
            # surrounding list entry.
            field_name = exc.field or f"modules[{idx}]"
            raise NSXConfigError(str(exc), field=field_name) from None
    return tuple(out)


@dataclass
class NsxProject:
    """Typed view of an app ``nsx.yml`` manifest.

    Construction is via :meth:`from_yaml` (or :meth:`from_mapping`),
    which validates the manifest structure up front and raises a typed
    :class:`NSXConfigError` carrying the offending ``.field`` path on
    any structural problem.

    The instance preserves the original mapping in :attr:`raw` so the
    ``nsx`` operations layer can keep its in-place mutation patterns
    (legacy from before the v1 freeze) until they are migrated. New
    code should use the typed properties below and :meth:`to_yaml` for
    round-trip writes.
    """

    path: Path
    raw: dict[str, Any]
    schema_version: int
    project: dict[str, Any]
    target: dict[str, Any]
    toolchain: str | None
    modules: tuple[AppModule, ...]
    module_registry: ModuleRegistryOverride
    tooling: dict[str, Any]
    profile: str | None
    profile_status: str | None
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    # --- Construction --------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> NsxProject:
        """Parse and validate an ``nsx.yml`` file at *path*.

        Raises:
            NSXConfigError: When the file is missing, unreadable,
                cannot be parsed as YAML, is not a mapping at the
                root, or fails any per-field structural check. The
                exception carries ``.field`` set to the offending YAML
                key path when the failure is field-scoped.
        """

        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise NSXConfigError(f"{path}: file not found") from exc
        except OSError as exc:
            raise NSXConfigError(f"{path}: cannot read file: {exc}") from exc
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise NSXConfigError(f"{path}: invalid YAML: {exc}") from None
        if loaded is None:
            raise NSXConfigError(f"{path}: file is empty or contains only comments")
        if not isinstance(loaded, dict):
            raise NSXConfigError(
                f"{path}: expected a YAML mapping at the root, got {type(loaded).__name__}"
            )
        return cls.from_mapping(loaded, path=path)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], *, path: Path | None = None) -> NsxProject:
        """Validate a pre-parsed mapping and build a typed instance.

        When *path* is supplied, error messages are prefixed with the
        actual file path so callers using :func:`load_project_config`
        on a non-default location see the offending file in the message
        body (the ``.field`` attribute already carries the YAML key
        path independently of *path*).
        """

        origin = str(path) if path is not None else "nsx.yml"

        if not isinstance(data, dict):
            raise NSXConfigError(
                f"{origin}: expected a mapping at the root, got {type(data).__name__}"
            )

        # schema_version: required at the top level, must equal the one
        # supported version (2).  ``None`` and missing are both rejected
        # explicitly so a typo (``shema_version``) doesn't silently default
        # through.
        if "schema_version" not in data:
            raise NSXConfigError(
                f"{origin}: missing required 'schema_version' "
                f"(this nsx requires schema_version {SUPPORTED_SCHEMA_VERSION})",
                field="schema_version",
            )
        sv_raw = data["schema_version"]
        if not isinstance(sv_raw, int) or isinstance(sv_raw, bool):
            raise NSXConfigError(
                f"{origin}: 'schema_version' must be an integer, got {type(sv_raw).__name__}",
                field="schema_version",
            )
        if sv_raw != SUPPORTED_SCHEMA_VERSION:
            raise NSXConfigError(
                f"{origin}: unsupported schema_version={sv_raw} "
                f"(this nsx requires schema_version {SUPPORTED_SCHEMA_VERSION}). "
                "v2 unifies dependencies under a single 'modules:' list with "
                "per-entry 'boards:' and 'source:'; the old 'requires:' field was removed.",
                field="schema_version",
            )

        project = _require_mapping(
            data.get("project"), field="project", allow_none=False, origin=origin
        )
        # project.name must exist and be a non-empty string.
        _require_str(project.get("name"), field="project.name", origin=origin)

        target = _require_mapping(
            data.get("target"), field="target", allow_none=True, origin=origin
        )
        if "board" in target:
            _require_str(target["board"], field="target.board", origin=origin)

        toolchain_value = data.get("toolchain")
        if toolchain_value is not None:
            toolchain_value = _require_str(toolchain_value, field="toolchain", origin=origin)

        modules = _validate_modules_list(data.get("modules"), origin=origin)

        registry_data = data.get("module_registry")
        if registry_data is not None and not isinstance(registry_data, dict):
            raise NSXConfigError(
                f"{origin}: 'module_registry' must be a mapping, "
                f"got {type(registry_data).__name__}",
                field="module_registry",
            )
        module_registry = ModuleRegistryOverride.from_mapping(registry_data)

        tooling = _require_mapping(
            data.get("tooling"), field="tooling", allow_none=True, origin=origin
        )

        profile_value = data.get("profile")
        if profile_value is not None and not isinstance(profile_value, str):
            raise NSXConfigError(
                f"{origin}: 'profile' must be a string when set, "
                f"got {type(profile_value).__name__}",
                field="profile",
            )

        profile_status_value = data.get("profile_status")
        if profile_status_value is not None and not isinstance(profile_status_value, str):
            raise NSXConfigError(
                f"{origin}: 'profile_status' must be a string when set, "
                f"got {type(profile_status_value).__name__}",
                field="profile_status",
            )

        _validate_targets(data.get("targets"), origin=origin)

        _validate_baseline(data.get("baseline"), origin=origin)

        # The additive ``requires:`` field was removed in schema v2 — reject it
        # with a migration hint rather than silently ignoring it.
        _reject_requires(data.get("requires"), field="requires", origin=origin)

        # Per-entry ``boards:`` must reference a declared supported target.
        _validate_module_boards_subset(data, modules, origin=origin)

        # Per-entry ``source:`` must declare a single, coherent source kind.
        _validate_module_sources(modules, origin=origin)

        extra = {k: v for k, v in data.items() if k not in _NSX_YML_KNOWN_TOP_LEVEL}

        return cls(
            path=Path(path) if path is not None else Path("nsx.yml"),
            raw=data,
            schema_version=sv_raw,
            project=project,
            target=target,
            toolchain=toolchain_value,
            modules=modules,
            module_registry=module_registry,
            tooling=tooling,
            profile=profile_value,
            profile_status=profile_status_value,
            extra=extra,
        )

    # --- Serialization -------------------------------------------------

    def to_mapping(self) -> dict[str, Any]:
        """Return a deep copy of the underlying raw mapping."""

        return copy.deepcopy(self.raw)

    def to_yaml(self, path: Path | None = None) -> str:
        """Serialize back to YAML, optionally writing to *path*.

        The on-disk shape is preserved up to formatting (whitespace,
        comments, key sort order is forced to insertion order). The
        round-trip property is: ``NsxProject.from_yaml(p).to_yaml(p2)``
        followed by ``NsxProject.from_yaml(p2)`` produces an
        equivalent typed instance — i.e. ``to_mapping()`` is equal.
        """

        text = yaml.safe_dump(self.raw, sort_keys=False, default_flow_style=False)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    # --- Convenience accessors ----------------------------------------

    @property
    def project_name(self) -> str:
        name = self.project.get("name")
        if not isinstance(name, str) or not name:
            raise NSXConfigError("nsx.yml missing project.name", field="project.name")
        return name

    @property
    def board(self) -> str | None:
        board = self.target.get("board") if isinstance(self.target, dict) else None
        return board if isinstance(board, str) and board else None

    @property
    def supported_boards(self) -> list[str]:
        """Board names of every declared build target (single- or multi-target)."""

        return list(self.app_config().targets())

    @property
    def default_board(self) -> str | None:
        """Board name of the default build target, or ``None`` if undeclared."""

        return self.app_config().default_board()

    def app_config(self) -> AppConfig:
        """Return the legacy :class:`AppConfig` view over the same mapping."""

        return AppConfig.from_mapping(self.raw)
