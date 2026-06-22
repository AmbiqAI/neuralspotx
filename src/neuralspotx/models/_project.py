"""Project / module registry entries and the legacy ``AppConfig`` view."""

from __future__ import annotations

import copy
from collections.abc import Iterable
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
    """User-facing ``source`` declaration from an app module entry.

    A dependency's *source* is where it comes from. Exactly one kind applies:

    * **registry** (default) -- resolved from the module registry; the entry
      carries no ``source`` block (an optional ``project`` / ``revision`` pin
      lives on the :class:`AppModule` itself).
    * **path** -- a local / editable checkout (``source: {path: ../foo}``).
    * **vendored** -- committed in-tree, never touched by sync
      (``source: {vendored: true}``).
    * **git** -- a pinned git remote (``source: {git: <url>, rev: <ref>}``).
    """

    path: str | None = None
    vendored: bool = False
    git: str | None = None
    rev: str | None = None
    extra: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ModuleSource:
        if not isinstance(data, dict):
            return cls()
        path = data.get("path")
        git = data.get("git")
        rev = data.get("rev")
        extra = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in {"path", "vendored", "git", "rev"}
        }
        return cls(
            path=path if isinstance(path, str) and path else None,
            vendored=data.get("vendored") is True,
            git=git if isinstance(git, str) and git else None,
            rev=rev if isinstance(rev, str) and rev else None,
            extra=extra or None,
        )

    def to_mapping(self) -> dict[str, Any]:
        out = copy.deepcopy(self.extra) if self.extra else {}
        if self.path:
            out["path"] = self.path
        if self.vendored:
            out["vendored"] = True
        if self.git:
            out["git"] = self.git
        if self.rev:
            out["rev"] = self.rev
        return out

    @property
    def kind(self) -> str:
        """The single source kind: ``path`` | ``vendored`` | ``git`` | ``registry``."""

        if self.path is not None:
            return "path"
        if self.vendored:
            return "vendored"
        if self.git is not None:
            return "git"
        return "registry"


@dataclass(frozen=True)
class AppModule:
    """One dependency entry from an app ``nsx.yml`` ``modules:`` list.

    A dependency is ``name`` + an optional **source** (where it comes from,
    see :class:`ModuleSource`) + an optional **boards** filter (which targets
    it applies to). An empty ``boards`` tuple means *all* supported targets;
    a non-empty tuple scopes the dependency to those boards (validated as a
    subset of ``targets.supported`` by the loader).
    """

    name: str
    project: str | None = None
    revision: str | None = None
    local: bool = False
    source: ModuleSource = ModuleSource()
    boards: tuple[str, ...] = ()
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
        boards_data = data.get("boards")
        boards: tuple[str, ...] = ()
        if boards_data is not None:
            if not isinstance(boards_data, list) or not all(
                isinstance(b, str) and b for b in boards_data
            ):
                raise NSXConfigError(
                    f"{origin}: modules[{index}].boards must be a list of board-name strings",
                    field=f"modules[{index}].boards",
                )
            boards = tuple(boards_data)
        extra = {
            k: copy.deepcopy(v)
            for k, v in data.items()
            if k not in {"name", "project", "revision", "local", "source", "boards"}
        }
        return cls(
            name=name,
            project=project if isinstance(project, str) and project else None,
            revision=revision if isinstance(revision, str) and revision else None,
            local=bool(data.get("local")),
            source=ModuleSource.from_mapping(
                source_data if isinstance(source_data, dict) else None
            ),
            boards=boards,
            extra=extra or None,
        )

    @property
    def is_local(self) -> bool:
        return self.local or self.source.path is not None

    @property
    def is_vendored(self) -> bool:
        return self.source.vendored

    @property
    def is_git(self) -> bool:
        return self.source.git is not None

    @property
    def is_opaque(self) -> bool:
        return self.is_local or self.is_vendored

    @property
    def source_kind(self) -> str:
        """The dependency's source kind: ``path`` | ``vendored`` | ``git`` | ``registry``."""

        if self.local and self.source.path is None:
            return "path"
        return self.source.kind

    def applies_to(self, board: str | None) -> bool:
        """True when this dependency applies to *board* (or to all targets).

        An empty ``boards`` filter (or a ``None`` board) means the dependency
        applies everywhere; otherwise it applies only to the listed boards.
        """

        if not self.boards or board is None:
            return True
        return board in self.boards

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
        if self.boards:
            out["boards"] = list(self.boards)
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
class RequiredModule:
    """An additive ``requires:`` entry — a module layered on the board profile.

    ``requires`` declares modules an app needs *on top of* its board's derived
    ``<board>_minimal`` profile (e.g. USB or timer modules). Entries are
    additive only: a bare ``name`` is resolved from the registry; an explicit
    ``project`` / ``revision`` pins it (and must agree with any
    ``module_registry`` override, per the alignment guard).
    """

    name: str
    project: str | None = None
    revision: str | None = None

    @classmethod
    def from_entry(cls, entry: Any, *, field: str, origin: str = "nsx.yml") -> RequiredModule:
        if isinstance(entry, str):
            if not entry:
                raise NSXConfigError(f"{origin}: '{field}' must be a non-empty string", field=field)
            return cls(name=entry)
        if isinstance(entry, dict):
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                raise NSXConfigError(f"{origin}: '{field}.name' must be a string", field=field)
            project = entry.get("project")
            revision = entry.get("revision")
            return cls(
                name=name,
                project=project if isinstance(project, str) and project else None,
                revision=revision if isinstance(revision, str) and revision else None,
            )
        raise NSXConfigError(
            f"{origin}: '{field}' must be a module name or a mapping, got {type(entry).__name__}",
            field=field,
        )

    def to_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {"name": self.name}
        if self.project:
            out["project"] = self.project
        if self.revision:
            out["revision"] = self.revision
        return out


def _dedupe_requires(items: Iterable[RequiredModule]) -> tuple[RequiredModule, ...]:
    """Dedupe ``requires`` entries by name, preserving first-seen order."""

    seen: set[str] = set()
    out: list[RequiredModule] = []
    for item in items:
        if item.name in seen:
            continue
        seen.add(item.name)
        out.append(item)
    return tuple(out)


@dataclass(frozen=True)
class ResolvedTarget:
    """A fully-resolved build target derived from an app manifest.

    Materialised either from an explicit ``targets:`` block or from the
    legacy singular ``target:`` / ``profile:`` keys. ``profile`` defaults to
    the board's derived starter profile (``<board>_minimal``); ``soc`` and
    ``toolchain`` are ``None`` when the manifest leaves them implicit, to be
    resolved from the board descriptor / global default downstream.
    ``requires`` is the complete set of additive modules for this target
    (global ``requires`` merged with the target's own), layered on the
    board profile during resolution.
    """

    board: str
    soc: str | None = None
    profile: str | None = None
    toolchain: str | None = None
    requires: tuple[RequiredModule, ...] = ()


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

    def _global_requires(self) -> tuple[RequiredModule, ...]:
        """Top-level ``requires:`` entries, applied to every target."""

        raw = self.raw.get("requires")
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise NSXConfigError("nsx.yml: 'requires' must be a list", field="requires")
        return _dedupe_requires(
            RequiredModule.from_entry(entry, field=f"requires[{idx}]")
            for idx, entry in enumerate(raw)
        )

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
                requires=self._global_requires(),
            )
        }

    def _targets_from_block(self, block: dict[str, Any]) -> dict[str, ResolvedTarget]:
        supported = block.get("supported", [])
        singular = self.target
        singular_board = singular.get("board") if isinstance(singular, dict) else None
        global_requires = self._global_requires()

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
            target_requires = cfg.get("requires")
            if target_requires is None:
                board_requires: tuple[RequiredModule, ...] = ()
            elif isinstance(target_requires, list):
                board_requires = tuple(
                    RequiredModule.from_entry(
                        entry, field=f"targets.supported.{board}.requires[{idx}]"
                    )
                    for idx, entry in enumerate(target_requires)
                )
            else:
                raise NSXConfigError(
                    f"nsx.yml: targets.supported.{board}.requires must be a list",
                    field=f"targets.supported.{board}.requires",
                )
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
                requires=_dedupe_requires((*global_requires, *board_requires)),
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

    def is_multi_target(self) -> bool:
        """True when the app declares an explicit ``targets:`` block.

        Multi-target apps key their committed lock per board
        (``nsx.<board>.lock``); single-target apps keep the legacy
        unsuffixed ``nsx.lock``.
        """

        return self._explicit_targets_block() is not None

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
            # Tolerate non-canonical board spellings (case / known alias):
            # the build path resolves targets with a ``normalize_board``-d
            # name while ``targets()`` is keyed by the raw manifest spelling.
            from ..constants import normalize_board

            norm = normalize_board(board)
            board = next((b for b in targets if normalize_board(b) == norm), board)
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

    # --- Unified dependency model (schema v2) -------------------------

    @property
    def baseline_disabled(self) -> bool:
        """True when ``baseline: none`` opts out of board-profile seeding.

        With the baseline disabled, the ``modules:`` list is the authoritative
        closure for the app rather than additive extras layered on the board's
        derived profile.
        """

        return str(self.raw.get("baseline") or "").strip().lower() == "none"

    def direct_modules(self, board: str | None = None) -> tuple[AppModule, ...]:
        """Declared direct dependencies that apply to *board*.

        Filters the ``modules:`` list by each entry's ``boards`` scope: an
        entry with no ``boards`` applies to every target; an entry with a
        ``boards`` list applies only to those boards. A ``None`` board returns
        every declared dependency (used where the active board is irrelevant).
        """

        return tuple(module for module in self.modules if module.applies_to(board))
