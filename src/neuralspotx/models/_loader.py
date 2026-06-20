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
    "requires",
)

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


def _validate_requires(value: Any, *, field: str, origin: str = "nsx.yml") -> None:
    """Validate a ``requires:`` list (top-level or per-target).

    Each entry is a module name string or a mapping carrying at least a
    ``name``. Structural-only: resolution and dedupe live in
    :class:`AppConfig`.
    """

    if value is None:
        return
    if not isinstance(value, list):
        raise NSXConfigError(
            f"{origin}: '{field}' must be a list, got {type(value).__name__}",
            field=field,
        )
    for idx, entry in enumerate(value):
        item_field = f"{field}[{idx}]"
        if isinstance(entry, str):
            _require_str(entry, field=item_field, origin=origin)
        elif isinstance(entry, dict):
            _require_str(entry.get("name"), field=f"{item_field}.name", origin=origin)
            for key in ("project", "revision"):
                if entry.get(key) is not None:
                    _require_str(entry[key], field=f"{item_field}.{key}", origin=origin)
        else:
            raise NSXConfigError(
                f"{origin}: '{item_field}' must be a module name or a mapping, "
                f"got {type(entry).__name__}",
                field=item_field,
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
            _validate_requires(
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

        # schema_version: required at the top level, must equal the
        # one supported version (1).  ``None`` and missing are both
        # rejected explicitly so a typo (``shema_version``) doesn't
        # silently default through.
        if "schema_version" not in data:
            raise NSXConfigError(
                f"{origin}: missing required 'schema_version' (this nsx supports v1)",
                field="schema_version",
            )
        sv_raw = data["schema_version"]
        if not isinstance(sv_raw, int) or isinstance(sv_raw, bool):
            raise NSXConfigError(
                f"{origin}: 'schema_version' must be an integer, got {type(sv_raw).__name__}",
                field="schema_version",
            )
        if sv_raw != 1:
            raise NSXConfigError(
                f"{origin}: unsupported schema_version={sv_raw} (this nsx supports v1)",
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

        requires_value = data.get("requires")
        _validate_requires(requires_value, field="requires", origin=origin)
        if data.get("modules") is not None and requires_value:
            raise NSXConfigError(
                f"{origin}: 'modules' (authoritative closure) and 'requires' (additive "
                "extras layered on the board profile) are mutually exclusive; remove one.",
                field="requires",
            )

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
