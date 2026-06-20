"""Project / module registry entries and the legacy ``AppConfig`` view."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .._errors import NSXConfigError


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


def _starter_profile_default(board: str) -> str:
    """Name of the derived starter profile for *board* (``<board>_minimal``)."""

    return f"{board}_minimal"


@dataclass(frozen=True)
class ResolvedTarget:
    """A fully-resolved build target derived from an app manifest.

    Materialised either from an explicit ``targets:`` block or from the
    legacy singular ``target:`` / ``profile:`` keys. ``profile`` defaults to
    the board's derived starter profile (``<board>_minimal``); ``soc`` and
    ``toolchain`` are ``None`` when the manifest leaves them implicit, to be
    resolved from the board descriptor / global default downstream.
    """

    board: str
    soc: str | None = None
    profile: str | None = None
    toolchain: str | None = None


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

    # --- Multi-target resolution --------------------------------------

    def _explicit_targets_block(self) -> dict[str, Any] | None:
        targets = self.raw.get("targets")
        return targets if isinstance(targets, dict) else None

    def _targets_from_singular(self) -> dict[str, ResolvedTarget]:
        target = self.target
        board = target.get("board")
        if not isinstance(board, str) or not board:
            return {}
        soc = target.get("soc")
        profile = self.raw.get("profile")
        return {
            board: ResolvedTarget(
                board=board,
                soc=soc if isinstance(soc, str) and soc else None,
                profile=(
                    profile
                    if isinstance(profile, str) and profile
                    else _starter_profile_default(board)
                ),
                toolchain=self.toolchain,
            )
        }

    def _targets_from_block(self, block: dict[str, Any]) -> dict[str, ResolvedTarget]:
        supported = block.get("supported", [])
        singular = self.target
        singular_board = singular.get("board") if isinstance(singular, dict) else None

        entries: dict[str, dict[str, Any]] = {}
        if isinstance(supported, list):
            for item in supported:
                if not isinstance(item, str) or not item:
                    raise NSXConfigError(
                        "nsx.yml: targets.supported list entries must be board-name strings",
                        field="targets.supported",
                    )
                entries[item] = {}
        elif isinstance(supported, dict):
            for board, cfg in supported.items():
                if not isinstance(board, str) or not board:
                    raise NSXConfigError(
                        "nsx.yml: targets.supported keys must be board names",
                        field="targets.supported",
                    )
                entries[board] = cfg if isinstance(cfg, dict) else {}
        else:
            raise NSXConfigError(
                "nsx.yml: targets.supported must be a list or a mapping",
                field="targets.supported",
            )

        out: dict[str, ResolvedTarget] = {}
        for board, cfg in entries.items():
            soc = cfg.get("soc")
            if not (isinstance(soc, str) and soc) and board == singular_board:
                soc = singular.get("soc")
            profile = cfg.get("profile")
            toolchain = cfg.get("toolchain")
            out[board] = ResolvedTarget(
                board=board,
                soc=soc if isinstance(soc, str) and soc else None,
                profile=(
                    profile
                    if isinstance(profile, str) and profile
                    else _starter_profile_default(board)
                ),
                toolchain=(
                    toolchain if isinstance(toolchain, str) and toolchain else self.toolchain
                ),
            )
        return out

    def targets(self) -> dict[str, ResolvedTarget]:
        """Resolve every declared build target, keyed by board name.

        Uses the explicit ``targets:`` block when present; otherwise derives
        a single target from the legacy ``target:`` / ``profile:`` keys so
        existing single-target manifests keep working unchanged.
        """

        block = self._explicit_targets_block()
        if block is not None:
            return self._targets_from_block(block)
        return self._targets_from_singular()

    def default_board(self) -> str | None:
        """Board name of the default build target, or ``None`` if undeclared."""

        block = self._explicit_targets_block()
        if block is not None:
            default = block.get("default")
            if isinstance(default, str) and default:
                return default
            return next(iter(self.targets()), None)
        board = self.target.get("board")
        return board if isinstance(board, str) and board else None

    def resolve_target(self, board: str | None = None) -> ResolvedTarget:
        """Return the :class:`ResolvedTarget` for *board* (or the default).

        Raises:
            NSXConfigError: When the app declares no target, or *board* is
                not among the supported targets.
        """

        targets = self.targets()
        if not targets:
            raise NSXConfigError("nsx.yml declares no build target", field="target")
        if board is None:
            board = self.default_board()
        if board not in targets:
            supported = ", ".join(sorted(targets)) or "(none)"
            raise NSXConfigError(
                f"board '{board}' is not a supported target (supported: {supported})",
                field="targets.supported",
            )
        return targets[board]

    def module_names(self) -> list[str]:
        return [module.name for module in self.modules]

    def local_module_names(self) -> set[str]:
        return {module.name for module in self.modules if module.is_local}

    def vendored_module_names(self) -> set[str]:
        return {module.name for module in self.modules if module.is_vendored}

    def opaque_modules(self) -> dict[str, AppModule]:
        return {module.name: module for module in self.modules if module.is_opaque}
