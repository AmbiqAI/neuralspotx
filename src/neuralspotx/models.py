"""Typed internal models for NSX registry, manifest, and app metadata."""

from __future__ import annotations

import copy
import dataclasses
import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ._errors import NSXConfigError


@dataclass(frozen=True)
class ProjectEntry:
    """A project entry from the packaged registry or app overrides."""

    name: str
    url: str | None = None
    revision: str | None = None
    path: str | None = None
    local_path: str | None = None

    @classmethod
    def from_mapping(
        cls,
        name: str,
        data: dict[str, Any] | None,
        *,
        default_revision: str | None = None,
    ) -> ProjectEntry:
        """Build a typed project entry from a manifest or registry mapping.

        Args:
            name: Project name key.
            data: Raw mapping loaded from YAML metadata.
            default_revision: Default revision to apply when the mapping omits one.

        Returns:
            A normalized ``ProjectEntry`` instance.
        """

        if not isinstance(data, dict):
            return cls(name=name, revision=default_revision)
        revision = data.get("revision")
        if not isinstance(revision, str) or not revision:
            revision = default_revision
        url = data.get("url")
        path = data.get("path")
        local_path = data.get("local_path")
        return cls(
            name=name,
            url=url if isinstance(url, str) and url else None,
            revision=revision,
            path=path if isinstance(path, str) and path else None,
            local_path=local_path if isinstance(local_path, str) and local_path else None,
        )

    def to_mapping(self) -> dict[str, str]:
        """Serialize the project entry back to an app/manifest mapping."""

        out = {"name": self.name}
        if self.url:
            out["url"] = self.url
        if self.revision:
            out["revision"] = self.revision
        if self.path:
            out["path"] = self.path
        if self.local_path:
            out["local_path"] = self.local_path
        return out


@dataclass(frozen=True)
class ModuleEntry:
    """An app-local module registry entry."""

    name: str
    project: str
    revision: str
    metadata: str | None = None

    def to_mapping(self) -> dict[str, str]:
        """Serialize the module entry back to an app-local registry mapping."""

        out = {
            "project": self.project,
            "revision": self.revision,
        }
        if self.metadata:
            out["metadata"] = self.metadata
        return out


@dataclass(frozen=True)
class ModuleSource:
    """User-facing ``source`` declaration from an app module entry."""

    path: str | None = None
    vendored: bool = False
    extra: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ModuleSource:
        if not isinstance(data, dict):
            return cls()
        path = data.get("path")
        extra = {k: copy.deepcopy(v) for k, v in data.items() if k not in {"path", "vendored"}}
        return cls(
            path=path if isinstance(path, str) and path else None,
            vendored=data.get("vendored") is True,
            extra=extra or None,
        )

    def to_mapping(self) -> dict[str, Any]:
        out = copy.deepcopy(self.extra) if self.extra else {}
        if self.path:
            out["path"] = self.path
        if self.vendored:
            out["vendored"] = True
        return out


@dataclass(frozen=True)
class AppModule:
    """One module entry from an app ``nsx.yml`` manifest."""

    name: str
    project: str | None = None
    revision: str | None = None
    local: bool = False
    source: ModuleSource = ModuleSource()
    extra: dict[str, Any] | None = None

    @classmethod
    def from_mapping(
        cls, index: int, data: dict[str, Any], *, origin: str = "nsx.yml"
    ) -> AppModule:
        if not isinstance(data, dict):
            raise NSXConfigError(
                f"{origin}: modules[{index}] must be a mapping",
                field=f"modules[{index}]",
            )
        name = data.get("name")
        if not isinstance(name, str):
            raise NSXConfigError(
                f"{origin}: modules[{index}].name must be a string",
                field=f"modules[{index}].name",
            )
        project = data.get("project")
        revision = data.get("revision")
        source_data = data.get("source")
        extra = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in {"name", "project", "revision", "local", "source"}
        }
        return cls(
            name=name,
            project=project if isinstance(project, str) and project else None,
            revision=revision if isinstance(revision, str) and revision else None,
            local=bool(data.get("local")),
            source=ModuleSource.from_mapping(
                source_data if isinstance(source_data, dict) else None
            ),
            extra=extra or None,
        )

    @property
    def is_local(self) -> bool:
        return self.local or self.source.path is not None

    @property
    def is_vendored(self) -> bool:
        return self.source.vendored

    @property
    def is_opaque(self) -> bool:
        return self.is_local or self.is_vendored

    def to_mapping(self) -> dict[str, Any]:
        out = copy.deepcopy(self.extra) if self.extra else {}
        out["name"] = self.name
        if self.project:
            out["project"] = self.project
        if self.revision:
            out["revision"] = self.revision
        if self.local:
            out["local"] = True
        source = self.source.to_mapping()
        if source:
            out["source"] = source
        return out


@dataclass(frozen=True)
class ModuleRegistryOverride:
    """App-local ``module_registry`` override block from ``nsx.yml``."""

    projects: dict[str, dict[str, Any]]
    modules: dict[str, dict[str, Any]]

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ModuleRegistryOverride:
        if not isinstance(data, dict):
            return cls(projects={}, modules={})
        projects = data.get("projects", {})
        modules = data.get("modules", {})
        return cls(
            projects={
                name: copy.deepcopy(value)
                for name, value in projects.items()
                if isinstance(name, str) and isinstance(value, dict)
            }
            if isinstance(projects, dict)
            else {},
            modules={
                name: copy.deepcopy(value)
                for name, value in modules.items()
                if isinstance(name, str) and isinstance(value, dict)
            }
            if isinstance(modules, dict)
            else {},
        )

    def merge_into(self, base_registry: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(base_registry)
        merged.setdefault("projects", {})
        merged.setdefault("modules", {})
        for name, override in self.projects.items():
            current = merged["projects"].get(name, {})
            if not isinstance(current, dict):
                current = {}
            current.update(override)
            merged["projects"][name] = current
        for name, override in self.modules.items():
            current = merged["modules"].get(name, {})
            if not isinstance(current, dict):
                current = {}
            current.update(override)
            merged["modules"][name] = current
        return merged


@dataclass(frozen=True)
class AppConfig:
    """Typed view of an app ``nsx.yml`` mapping."""

    raw: dict[str, Any]
    modules: tuple[AppModule, ...]
    registry_overrides: ModuleRegistryOverride

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AppConfig:
        modules_data = data.get("modules", [])
        if not isinstance(modules_data, list):
            raise NSXConfigError("nsx.yml: 'modules' must be a list")
        return cls(
            raw=data,
            modules=tuple(
                AppModule.from_mapping(idx, item) for idx, item in enumerate(modules_data)
            ),
            registry_overrides=ModuleRegistryOverride.from_mapping(data.get("module_registry")),
        )

    @property
    def project_name(self) -> str:
        project = self.raw.get("project", {})
        name = project.get("name") if isinstance(project, dict) else None
        if not isinstance(name, str) or not name:
            raise NSXConfigError("nsx.yml missing project.name")
        return name

    @property
    def target(self) -> dict[str, Any]:
        target = self.raw.get("target", {})
        return target if isinstance(target, dict) else {}

    @property
    def toolchain(self) -> str | None:
        toolchain = self.raw.get("toolchain")
        return toolchain if isinstance(toolchain, str) and toolchain else None

    def module_names(self) -> list[str]:
        return [module.name for module in self.modules]

    def local_module_names(self) -> set[str]:
        return {module.name for module in self.modules if module.is_local}

    def vendored_module_names(self) -> set[str]:
        return {module.name for module in self.modules if module.is_vendored}

    def opaque_modules(self) -> dict[str, AppModule]:
        return {module.name: module for module in self.modules if module.is_opaque}


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

    def app_config(self) -> AppConfig:
        """Return the legacy :class:`AppConfig` view over the same mapping."""

        return AppConfig.from_mapping(self.raw)


# ------------------------------------------------------------------
# CLI command descriptors
# ------------------------------------------------------------------


class CommandCategory(str, enum.Enum):
    """Category tag for CLI command graph hints."""

    ENTRYPOINT = "entrypoint"
    DISCOVERY = "discovery"
    APP_CREATION = "app-creation"
    DIAGNOSTICS = "diagnostics"
    BUILD = "build"
    DEPLOY = "deploy"
    MODULES = "modules"
    MAINTENANCE = "maintenance"


class CommandScope(str, enum.Enum):
    """Scope tag for CLI command graph hints."""

    GLOBAL = "global"
    APP = "app"
    ENVIRONMENT = "environment"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True)
class CommandHint:
    """Typed metadata hint for a CLI command in the command graph."""

    category: CommandCategory
    scope: CommandScope
    next_commands: tuple[str, ...] = ()
    alias_for: str | None = None

    def to_dict(self) -> dict[str, str | list[str]]:
        out: dict[str, str | list[str]] = {
            "category": self.category.value,
            "scope": self.scope.value,
            "next_commands": list(self.next_commands),
        }
        if self.alias_for is not None:
            out["alias_for"] = self.alias_for
        return out


@dataclass(frozen=True)
class DoctorCheck:
    """One environment / toolchain check produced by ``api.doctor()``.

    *required* discriminates checks that gate ``ok`` (e.g. ``cmake``)
    from informational ones (e.g. ATfE when ``ATFE_ROOT`` is set, or
    individual armclang components when the toolchain was detected).
    """

    label: str
    ok: bool
    required: bool = True
    detail: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "ok": self.ok,
            "required": self.required,
            "detail": self.detail,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class DoctorReport:
    """Aggregate result returned by ``api.doctor()``.

    ``ok`` is ``True`` iff every *required* check passed.
    ``checks`` preserves the order in which checks ran so embedders can
    render a deterministic table. ``notes`` carries free-form lines
    (e.g. "ATfE toolchain not detected — optional") for parity with the
    historic CLI output.
    """

    checks: tuple[DoctorCheck, ...]
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "notes": list(self.notes),
        }


# ------------------------------------------------------------------
# Outdated report (api.outdated_app)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class OutdatedModule:
    """One git-hosted module's drift between locked commit and upstream tip.

    *status* is a ``str``-mixed enum value (``OutdatedStatus``) so plain
    string comparisons against ``"up-to-date"`` / ``"outdated"`` keep
    working for embedders that don't import the enum.
    """

    name: str
    constraint: str
    locked: str
    upstream: str
    status: str
    url: str = ""

    @property
    def is_outdated(self) -> bool:
        return self.status == "outdated"

    def to_dict(self) -> dict[str, str]:
        return {
            "module": self.name,
            "constraint": self.constraint,
            "locked": self.locked,
            "upstream": self.upstream,
            "status": str(self.status),
            "url": self.url,
        }


@dataclass(frozen=True)
class OutdatedSkip:
    """A module that ``api.outdated_app`` could not check, with a reason."""

    name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"module": self.name, "reason": self.reason}


@dataclass(frozen=True)
class OutdatedReport:
    """Aggregate result returned by ``api.outdated_app()``.

    ``checked`` preserves the order in which modules were inspected so
    embedders can render a deterministic table; ``skipped`` records
    modules that could not be resolved (no URL, ``git ls-remote``
    failure, etc.). The ``outdated`` property is a convenience filter
    that mirrors what the historic CLI returned as an integer count.
    """

    checked: tuple[OutdatedModule, ...]
    skipped: tuple[OutdatedSkip, ...] = ()

    @property
    def outdated(self) -> tuple[OutdatedModule, ...]:
        return tuple(m for m in self.checked if m.is_outdated)

    @property
    def outdated_count(self) -> int:
        return len(self.outdated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": [m.to_dict() for m in self.checked],
            "skipped": [s.to_dict() for s in self.skipped],
            "outdated_count": self.outdated_count,
        }


# ------------------------------------------------------------------
# Module change records (api.add_module / remove_module / update_modules /
# register_module / init_module)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleChange:
    """One state-change applied to a module by an api.* mutation.

    Attributes:
        name: Module name.
        before: The recorded revision (or ``None`` when the module did
            not exist beforehand). May be ``None`` for ``init_module``
            since there is no app-side state.
        after: The resolved revision after the operation (or ``None``
            when the module was removed).
        action: One of ``"added"``, ``"removed"``, ``"updated"``,
            ``"noop"``. ``"added"`` covers ``add_module``/
            ``register_module``/``init_module`` and any transitive
            dependencies pulled in. ``"removed"`` covers cascaded
            removals. ``"updated"`` is recorded by ``update_modules``
            when the resolved revision changed; ``"noop"`` when it did
            not.
        dry_run: ``True`` when the change was predicted by a
            ``dry_run=True`` call and not actually applied.
    """

    name: str
    before: str | None
    after: str | None
    action: str
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "action": self.action,
            "dry_run": self.dry_run,
        }


# ------------------------------------------------------------------
# Module discovery records
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SearchMatch:
    """A single field match from module search scoring."""

    field: str
    term: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "term": self.term, "value": self.value}


_DISCOVERY_RICH_FIELDS = ("module", "support", "build", "depends", "compatibility")
_DISCOVERY_SEMANTIC_FIELDS = (
    "summary",
    "capabilities",
    "use_cases",
    "anti_use_cases",
    "agent_keywords",
    "example_refs",
    "composition_hints",
    "provides",
    "constraints",
    "integrations",
)


@dataclass(frozen=True)
class DiscoveryRecord:
    """Typed module discovery record returned by list/describe/search APIs."""

    # Core fields (always present)
    name: str
    project: str
    revision: str
    metadata: str | None
    enabled: bool

    # Metadata availability
    metadata_available: bool = False
    metadata_error: str | None = None

    # Rich metadata (only when metadata_available is True)
    module: dict[str, Any] | None = None
    support: dict[str, Any] | None = None
    build: dict[str, Any] | None = None
    depends: dict[str, Any] | None = None
    compatibility: dict[str, Any] | None = None

    # Optional semantic metadata
    summary: str | None = None
    capabilities: list[str] | None = None
    use_cases: list[str] | None = None
    anti_use_cases: list[str] | None = None
    agent_keywords: list[str] | None = None
    example_refs: list[Any] | None = None
    composition_hints: dict[str, Any] | None = None
    provides: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None
    integrations: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict matching the legacy discovery record format."""
        out: dict[str, Any] = {
            "name": self.name,
            "project": self.project,
            "revision": self.revision,
            "metadata": self.metadata,
            "enabled": self.enabled,
        }
        if self.metadata_error is not None:
            out["metadata_available"] = False
            out["metadata_error"] = self.metadata_error
            return out
        if not self.metadata_available:
            return out
        out["metadata_available"] = True
        for field in _DISCOVERY_RICH_FIELDS:
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        for field in _DISCOVERY_SEMANTIC_FIELDS:
            value = getattr(self, field)
            if value is not None:
                out[field] = value
        return out


@dataclass(frozen=True)
class SearchResult(DiscoveryRecord):
    """A discovery record augmented with search scoring."""

    score: int = 0
    matches: tuple[SearchMatch, ...] = ()
    compatible: bool | None = None

    @classmethod
    def from_record(
        cls,
        record: DiscoveryRecord,
        *,
        score: int,
        matches: tuple[SearchMatch, ...],
        compatible: bool | None,
    ) -> SearchResult:
        base = {f.name: getattr(record, f.name) for f in dataclasses.fields(DiscoveryRecord)}
        return cls(**base, score=score, matches=matches, compatible=compatible)

    def to_dict(self) -> dict[str, Any]:
        out = super().to_dict()
        out["score"] = self.score
        out["matches"] = [m.to_dict() for m in self.matches]
        out["compatible"] = self.compatible
        return out


@dataclass(frozen=True)
class CacheEntry:
    """A single entry in the NSX module artifact cache."""

    digest: str
    path: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {"digest": self.digest, "path": self.path, "size_bytes": self.size_bytes}


@dataclass(frozen=True)
class CacheInfo:
    """Snapshot of the NSX module artifact cache."""

    root: str
    disabled: bool
    entries: tuple[CacheEntry, ...]

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def total_size_bytes(self) -> int:
        return sum(e.size_bytes for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "disabled": self.disabled,
            "entry_count": self.entry_count,
            "entries": [e.to_dict() for e in self.entries],
            "total_size_bytes": self.total_size_bytes,
        }


@dataclass(frozen=True)
class CacheCleanResult:
    """Outcome of an :func:`api.clean_cache` invocation."""

    root: str
    removed_count: int
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "removed_count": self.removed_count,
            "dry_run": self.dry_run,
        }
