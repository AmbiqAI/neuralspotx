"""Clean generated builds and restorable module copies under the app writer lock."""

from __future__ import annotations

import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._build_ownership import initialized_by_app
from .._errors import NSXConfigError
from .._io import info
from ..constants import normalize_board
from ..file_lock import app_lock
from ..metadata import registry_entry_for_module
from ..models import AppConfig
from ..module_registry import _is_packaged_module, expand_profile_seeds, packaged_module_source_dir
from ..nsx_lock import (
    _HASH_EXCLUDE_DIRS,
    LockFile,
    LockKind,
    ResolvedModule,
    hash_manifest,
    hash_tree,
    read_lock_file,
)
from ..nsx_lock._models import is_locked_commit
from ..project_config import (
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _module_clone_dir,
    _registry_project_entry,
    _run_cmake_configure,
)
from ..subprocess_utils import run
from ._cmake_cache import read_owned_cache
from ._common import _resolve_build_context
from ._lock import _apply_active_target, _resolved_module_path


def _owned_build(app: Path, path: Path, board: str | None = None) -> bool:
    # A cache can be copied or left by an in-source build. The source and
    # binary directory must identify this exact, separate build.
    if (
        Path(os.path.abspath(path)) != path.resolve()
        or app.is_relative_to(path.resolve())
        or (path / "CMakeLists.txt").exists()
    ):
        return False
    path = path.resolve()
    if any(
        path.is_relative_to(app / name) for name in ("modules", "boards", "cmake", ".nsx", ".git")
    ):
        return False
    if (path / "nsx.yml").exists() or (path / ".git").exists():
        return False
    if not initialized_by_app(app, path):
        return False
    try:
        selected = read_owned_cache(app, path).get("NSX_BOARD")
    except NSXConfigError:
        return False
    return bool(selected and (board is None or selected == board))


@dataclass(frozen=True)
class _ModuleCopy:
    project: str
    kind: LockKind
    origin: str
    revision: str
    digest: str


def _restorable_copy(
    app: Path, path: Path, name: str, entry: ResolvedModule, registry: dict[str, Any]
) -> _ModuleCopy | None:
    if entry.kind not in (LockKind.GIT, LockKind.PACKAGED):
        return None
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.content_hash):
        return None
    try:
        module = registry_entry_for_module(registry, name)
    except ValueError:
        return None
    project = _registry_project_entry(registry, module.project)
    if project.name != entry.project or project.local_path:
        return None
    if _resolved_module_path(app, name, registry) != path:
        return None
    if entry.kind == LockKind.GIT:
        if not entry.url or entry.url != project.url or not is_locked_commit(entry.commit):
            return None
        return _ModuleCopy(
            entry.project, entry.kind, entry.url, entry.commit or "", entry.content_hash
        )
    if not _is_packaged_module(registry, name):
        return None
    source = packaged_module_source_dir(name, module, registry)
    if not source.is_dir() or hash_tree(source) != entry.content_hash:
        return None
    return _ModuleCopy(entry.project, entry.kind, str(source), "", entry.content_hash)


def _overlap(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


def _unreceipted_content(path: Path) -> bool:
    # Lock hashes omit VCS state, environments, and filesystem link identity.
    # A matching hash alone cannot authorize removal of these objects.
    def raise_error(exc: OSError) -> None:
        raise exc

    for root, dirs, files in os.walk(path, onerror=raise_error):
        if not dirs and not files and Path(root) != path:
            return True  # The receipt records the root, but omits empty descendants.
        for name in (*dirs, *files):
            child = Path(root) / name
            if name in _HASH_EXCLUDE_DIRS or child.is_symlink():
                return True
            if not child.is_dir() and not child.is_file():
                return True
    return False


@dataclass
class _CleanupInputs:
    sources: set[Path]
    checkout_paths: dict[Path, set[str]]
    receipt: LockFile | None

    def protects_build(self, build: Path) -> bool:
        return any(_overlap(build, path) for path in self.sources.union(self.checkout_paths))

    def register_checkout(self, path: Path, project: str) -> None:
        for location in _input_paths(path):
            self.checkout_paths.setdefault(location, set()).add(project)

    def include_registry(self, app: Path, registry: dict[str, Any]) -> None:
        for key in registry["projects"]:
            project = _registry_project_entry(registry, key)
            if project.local_path:
                self.sources.update(_input_paths(Path(project.local_path)))
            self.register_checkout(_module_clone_dir(app, key, registry), key)

    def overlaps_other_checkout(self, path: Path, project: str) -> bool:
        return any(
            _overlap(path, other) and (path != other or owners != {project})
            for other, owners in self.checkout_paths.items()
        )


def _input_paths(path: Path) -> tuple[Path, Path]:
    # A declared symlink (or one of its parents) is itself an app input.
    return Path(os.path.abspath(path)), path.resolve()


def _cleanup_inputs(app: Path, cfg: dict[str, Any]) -> _CleanupInputs:
    """Include declared sources and checkout locations independently of receipt freshness."""
    inputs = _CleanupInputs(set(), {}, read_lock_file(app, require_known_kinds=True))
    for module in AppConfig.from_mapping(cfg).modules:
        if module.source.vendored or module.local:
            inputs.sources.update(_input_paths(app / "modules" / module.name))
        if module.source.path:
            inputs.sources.update(_input_paths(app / Path(module.source.path).expanduser()))
    authored_paths: set[Path] = set()
    registry = _effective_registry(
        _load_registry(), cfg, app_dir=app, authored_paths=authored_paths
    )
    for path in authored_paths:
        inputs.sources.update(_input_paths(path))
    inputs.include_registry(app, registry)
    if inputs.receipt:
        for section in inputs.receipt.targets.values():
            for entry in section.modules.values():
                inputs.register_checkout(app / entry.vendored_at.replace("\\", "/"), entry.project)
    return inputs


def _module_removals(
    app: Path, cfg: dict[str, Any], inputs: _CleanupInputs, *, force: bool
) -> list[Path]:
    root = app / "modules"
    if not root.is_dir() or root.is_symlink():
        return []
    protected: set[Path] = set()
    receipt = inputs.receipt
    if receipt is None:
        return []
    digest = hash_manifest(app / "nsx.yml")
    if any(section.manifest_hash != digest for section in receipt.targets.values()):
        info("Preserving modules/ because nsx.lock does not match nsx.yml.")
        return []

    project = AppConfig.from_mapping(cfg)
    if {normalize_board(board) for board in project.targets()} != set(receipt.targets):
        info("Preserving modules/ because nsx.lock does not cover the current board set.")
        return []
    base = _load_registry()
    copies: dict[Path, set[_ModuleCopy | None]] = defaultdict(set)
    for board, section in receipt.targets.items():
        active = (
            _apply_active_target(cfg, project.resolve_target(board))
            if project.is_multi_target()
            else cfg
        )
        active = expand_profile_seeds(active, base, app_dir=app)
        registry = _effective_registry(base, active, app_dir=app)
        inputs.include_registry(app, registry)
        for name, entry in section.modules.items():
            path = app / entry.vendored_at.replace("\\", "/")
            resolved = path.resolve()
            if path != resolved:
                protected.add(resolved)
                continue
            if path != root and path.is_relative_to(root):
                copies[path].add(_restorable_copy(app, path, name, entry, registry))
            else:
                protected.add(path)

    protected.update(inputs.sources)
    removals = []
    for path, claims in copies.items():
        if len(claims) != 1 or None in claims or not path.is_dir():
            continue
        if any(_overlap(path, other) for other in protected | (copies.keys() - {path})):
            continue
        claim = next(iter(claims))
        assert claim is not None
        if inputs.overlaps_other_checkout(path, claim.project):
            continue
        if _unreceipted_content(path):
            info(f"Preserving {path} because it contains files outside the lock hash.")
            continue
        if not force and hash_tree(path) != claim.digest:
            raise NSXConfigError(
                f"Refusing to reset: {path} differs from nsx.lock. "
                "Save your changes or use --force to discard edits to this dependency."
            )
        removals.append(path)
    return removals


def _reset_app(app: Path, *, force: bool) -> Path:
    if not (app / "nsx.yml").is_file():
        raise NSXConfigError(f"--reset requires an app directory containing nsx.yml: {app}")
    with app_lock(app):
        cfg = _load_app_cfg(app)
        inputs = _cleanup_inputs(app, cfg)
        removals = _module_removals(app, cfg, inputs, force=force)
        builds = app / "build"
        candidates = list(app.glob("build_*"))
        if _owned_build(app, builds):
            candidates.append(builds)
        elif builds.is_dir() and not builds.is_symlink():
            candidates.extend(builds.iterdir())
        removals.extend(
            path
            for path in candidates
            if _owned_build(app, path) and not inputs.protects_build(path)
        )
        for path in removals:
            shutil.rmtree(path)
            info(f"Removed {path}")
    return app


def clean_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
    toolchain: str | None = None,
    full: bool = False,
    reset: bool = False,
    force: bool = False,
) -> Path:
    """Clean a build, or reset confirmed app-owned generated directories."""
    if reset:
        return _reset_app(app_dir.expanduser().resolve(), force=force)
    app, _, selected, build = _resolve_build_context(app_dir, board=board, build_dir=build_dir)
    build = build.absolute()
    if not build.exists():
        return build
    if full:
        with app_lock(app):
            if not build.exists():
                return build
            if not _owned_build(app, build, selected) or _cleanup_inputs(
                app, _load_app_cfg(app)
            ).protects_build(build.resolve()):
                raise NSXConfigError(
                    f"Cannot confirm {build} is an owned build for {selected}. "
                    "Inspect its contents and CMakeCache.txt before removing it manually."
                )
            build = build.resolve()
            shutil.rmtree(build)
        info(f"Removed build directory: {build}")
    else:
        if not (build / "build.ninja").exists():
            _run_cmake_configure(app, build, selected, toolchain=toolchain)
        run(["cmake", "--build", str(build), "--target", "clean"])
    return build
