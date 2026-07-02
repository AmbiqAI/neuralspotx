"""Module sync — make ``modules/`` match ``nsx.lock``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError, NSXIntegrityError, NSXModuleError
from .._io import info
from .._logging import get_logger
from ..file_lock import app_lock
from ..models import AppConfig
from ..module_registry import _update_module_clone, expand_profile_seeds
from ..nsx_lock import (
    NSX_TOOLING_AUTOGEN_FILES,
    LockKind,
    ResolvedModule,
    hash_manifest,
    hash_tree,
    lock_path,
    read_lock,
    read_lock_file,
)
from ..project_config import (
    _board_key_for_app,
    _copy_packaged_tree,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _registry_project_entry,
    _write_app_module_file,
    _write_cmake_nsx_gitignore,
    _write_modules_gitignore_for_module_names,
    validate_app_module_alignment,
)
from ._lock import _apply_active_target, _resolved_module_path, lock_app_impl

_log = get_logger(__name__)


def _locked_module_union(app_dir: Path, active_modules: list[str]) -> list[str]:
    """Return active modules followed by sibling-target-only locked modules."""

    union = list(active_modules)
    lock_file = read_lock_file(app_dir)
    if lock_file is None:
        return union
    for target_lock in lock_file.targets.values():
        for name in target_lock.modules:
            if name not in union:
                union.append(name)
    return union


def _ensure_app_modules(app_dir: Path, board: str | None = None) -> None:
    """Ensure all modules declared in nsx.yml are present on disk.

    This is called during ``nsx configure`` so that a freshly-cloned app
    (whose registry modules are gitignored) can be configured without
    a separate ``nsx module add`` or ``nsx module update`` step.

    The lock file is the single source of truth: ``sync_app_impl``
    handles both the lock-present and lock-missing cases. When the
    lock is missing, it creates the lock and then vendors modules
    according to the resolved lock; it does not rewrite the lock
    after vendoring (``content_hash`` is the upstream-artifact hash,
    so it is correct from the start under v3).
    """

    sync_app_impl(app_dir, board=board)


def regenerate_active_board_glue(app_dir: Path, board: str | None = None) -> None:
    """Refresh the active board's CMake glue without re-vendoring modules.

    The generated glue (``cmake/nsx/modules.cmake`` + ``modules/.gitignore``)
    lives at a board-agnostic path but its content is board-specific: the
    ``NSX_APP_MODULES`` list differs per board. Because ``build`` / ``flash``
    / ``view`` only run a full sync when ``build.ninja`` is missing,
    alternating builds across boards would otherwise reconfigure against the
    previously-synced board's stale module list (e.g. an Apollo5-only
    ``nsx-pmu-armv8m`` leaking into an Apollo4 build).

    This is a cheap, idempotent refresh: it reads the active board's lock for
    the authoritative module set and rewrites the glue only when it actually
    changed. It does not hash or re-vendor module trees. When no lock exists
    yet it is a no-op — the full sync path will create one.
    """

    board_key = _board_key_for_app(app_dir, board)
    lock = read_lock(app_dir, board_key)
    if lock is None:
        return
    nsx_cfg = _load_app_cfg(app_dir)
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    if app_cfg.is_multi_target():
        nsx_cfg = _apply_active_target(nsx_cfg, app_cfg.resolve_target(board))
    nsx_cfg = expand_profile_seeds(nsx_cfg, _load_registry())
    ordered_modules = list(lock.modules)
    _write_app_module_file(app_dir, nsx_cfg, module_names=ordered_modules)
    _write_modules_gitignore_for_module_names(
        app_dir, nsx_cfg, _locked_module_union(app_dir, ordered_modules))



def sync_app_impl(
    app_dir: Path,
    *,
    board: str | None = None,
    frozen: bool = False,
    force: bool = False,
) -> None:
    """Make ``modules/`` exactly match ``nsx.lock``.

    Pure: ``sync_app_impl`` never modifies ``nsx.lock``. The lock is
    written exclusively by ``nsx lock`` (and by the implicit ``nsx
    lock`` invocation here when no lock exists yet). For each module,
    sync materializes the upstream artifact recorded in the lock into
    ``modules/<name>/``. If the on-disk tree already matches what the
    upstream would produce, nothing is written.

    Args:
        frozen: Read-only mode. Verify that the on-disk vendored tree
            matches each lock entry's ``content_hash`` and raise
            :class:`NSXError` on any mismatch instead of correcting it.
            Also raises if ``nsx.yml`` has changed since ``nsx.lock``
            was written (manifest-hash drift). This does NOT detect
            upstream drift on its own — ``nsx outdated`` is the tool
            for comparing the lock against current upstream HEADs.
        force: Re-vendor every fetchable module even if its on-disk
            tree already matches the locked content_hash.
    """

    with app_lock(app_dir):
        _sync_app_impl_unlocked(app_dir, board=board, frozen=frozen, force=force)


@dataclass(frozen=True, slots=True)
class _SyncContext:
    """Immutable inputs shared by every per-entry sync handler.

    Bundling these avoids threading the same values through each handler.
    The handlers below are otherwise free functions so each ``LockKind``
    branch can be read (and tested) in isolation from the orchestration
    loop in :func:`_sync_app_impl_unlocked`.
    """

    app_dir: Path
    registry: dict[str, Any]
    cmake_nsx: Path
    frozen: bool
    force: bool


def _resolve_vendored_dir(ctx: _SyncContext, name: str, entry: ResolvedModule) -> Path:
    """Resolve the on-disk destination directory for a lock entry.

    Vendored / unresolved entries don't necessarily have a registry
    entry; trust the path recorded in the lock for those. Local entries
    may also be locked without a registry entry (e.g. ``nsx module add
    --local`` writes ``local: true`` without an override) — fall back to
    the lock-recorded path in that case so ``_resolved_module_path()``
    doesn't raise.
    """

    if entry.kind in (LockKind.VENDORED, LockKind.UNRESOLVED):
        return ctx.app_dir / entry.vendored_at
    if entry.kind == LockKind.LOCAL:
        try:
            return _resolved_module_path(ctx.app_dir, name, ctx.registry)
        except ValueError:
            # ``registry_entry_for_module`` raises ``ValueError`` when the
            # module isn't in the registry. Trust the lock-recorded path.
            return ctx.app_dir / entry.vendored_at
    return _resolved_module_path(ctx.app_dir, name, ctx.registry)


def _sync_vendored_entry(
    ctx: _SyncContext,
    name: str,
    entry: ResolvedModule,
    vendored_dir: Path,
    vendored_paths: set[Path],
) -> None:
    """Vendored entry: the source IS ``modules/<name>/``; verify only."""

    if not vendored_dir.exists():
        # Vendored modules are not fetchable -- the source IS the in-tree
        # directory. A missing path means the user deleted committed
        # content; sync cannot repair it without a checkout/restore.
        raise NSXModuleError(
            f"Vendored module '{name}' is missing on disk "
            f"({entry.vendored_at}). Restore the directory "
            "(e.g. `git checkout -- modules/`) before running sync."
        )
    on_disk_hash = hash_tree(vendored_dir)
    if on_disk_hash != entry.content_hash:
        msg = (
            f"Vendored module '{name}' content drifted from lock "
            f"({entry.vendored_at}). Run `nsx lock` to re-record, "
            "or revert the changes."
        )
        if ctx.frozen:
            raise NSXIntegrityError(msg, module=name)
        _log.warning("%s", msg)
    vendored_paths.add(vendored_dir)


def _sync_unresolved_entry(
    ctx: _SyncContext,
    name: str,
    entry: ResolvedModule,
    vendored_dir: Path,
    vendored_paths: set[Path],
) -> None:
    """Unresolved entry: upstream unreachable; verify only."""

    if not vendored_dir.exists():
        # Upstream is unreachable by definition for unresolved entries;
        # we cannot repair a missing tree from any source.
        raise NSXModuleError(
            f"Unresolved module '{name}' is missing on disk "
            f"({entry.vendored_at}) and upstream {entry.url} is "
            "unreachable. Restore the vendored directory or "
            "re-run `nsx lock` with network access to resolve."
        )
    on_disk_hash = hash_tree(vendored_dir)
    if on_disk_hash != entry.content_hash:
        msg = (
            f"Unresolved module '{name}' content drifted from lock "
            f"({entry.vendored_at}); upstream {entry.url} is not reachable."
        )
        if ctx.frozen:
            raise NSXIntegrityError(msg, module=name)
        _log.warning("%s", msg)
    vendored_paths.add(vendored_dir)


def _verify_duplicate_path(
    ctx: _SyncContext,
    name: str,
    entry: ResolvedModule,
    vendored_dir: Path,
) -> None:
    """Two lock entries resolve to one path: verify, don't re-vendor.

    The first entry already vendored the path; subsequent entries only
    confirm what's on disk matches their own expected hash.
    """

    current_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
    if current_hash != entry.content_hash:
        msg = (
            f"Module '{name}' expects content_hash {entry.content_hash} "
            f"at {entry.vendored_at}, but that path was already vendored "
            f"for another module with hash {current_hash}. "
            "Multiple nsx.lock entries resolve to the same vendored "
            "path but disagree on its content; run `nsx lock` to "
            "refresh the lock."
        )
        if ctx.frozen:
            raise NSXIntegrityError(msg, module=name)
        _log.warning("%s", msg)


def _sync_local_entry(
    ctx: _SyncContext,
    name: str,
    entry: ResolvedModule,
    vendored_dir: Path,
    vendored_paths: set[Path],
) -> int:
    """Local entry: upstream is a source path or ``modules/<name>/``.

    Returns the number of modules re-mirrored (0 or 1).
    """

    from ..module_registry import _vendor_local_module_into_app

    try:
        project_entry = _registry_project_entry(ctx.registry, entry.project)
    except (ValueError, KeyError, TypeError):
        project_entry = None

    if project_entry is not None and project_entry.local_path:
        # ``content_hash`` is the hash of the upstream source directory
        # (``project_entry.local_path``), not the vendored mirror. Compare
        # against the live source tree to detect upstream drift; compare
        # on-disk vs source to decide whether the mirror needs an update.
        # (Bug fix: previously we compared ``hash_tree(vendored_dir) ==
        # entry.content_hash``, which silently skipped re-mirroring when
        # source had drifted to a hash equal to the lock's old value.)
        source_dir = Path(project_entry.local_path).expanduser().resolve()
        if not source_dir.exists():
            raise NSXModuleError(
                f"Local source for module '{name}' is missing: "
                f"{source_dir} does not exist. "
                f"Restore the path or re-register the project with "
                f"`nsx module register --project-local-path`."
            )
        source_hash = hash_tree(source_dir)
        on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None

        # Detect upstream-source drift since lock.
        if source_hash != entry.content_hash:
            msg = (
                f"Local source for '{name}' at {source_dir} has drifted "
                f"since lock (expected {entry.content_hash}, got "
                f"{source_hash}); run `nsx lock` to re-record."
            )
            if ctx.frozen:
                raise NSXModuleError(msg)
            _log.warning("%s", msg)

        # Mirror is already in sync with current source: skip.
        if not ctx.force and on_disk_hash == source_hash:
            vendored_paths.add(vendored_dir)
            return 0

        if ctx.frozen:
            raise NSXModuleError(
                f"Local module '{name}' mirror at {entry.vendored_at} "
                f"does not match source {source_dir}. Refusing under "
                "--frozen."
            )
        _vendor_local_module_into_app(ctx.app_dir, name, ctx.registry)
        vendored_paths.add(vendored_dir)
        return 1

    # In-tree local (no source path): source IS modules/<name>/.
    # Verify only, like vendored.
    on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
    if on_disk_hash != entry.content_hash:
        msg = (
            f"Local module '{name}' content drifted from lock "
            f"({entry.vendored_at}). Run `nsx lock` to re-record, "
            "or revert the changes."
        )
        if ctx.frozen:
            raise NSXIntegrityError(msg, module=name)
        _log.warning("%s", msg)
    vendored_paths.add(vendored_dir)
    return 0


def _sync_fetchable_entry(
    ctx: _SyncContext,
    name: str,
    entry: ResolvedModule,
    vendored_dir: Path,
    vendored_paths: set[Path],
) -> int:
    """Packaged / git entry: fetchable upstream artifact.

    Returns the number of modules re-vendored (0 or 1).
    """

    from ..module_registry import (
        _vendor_git_module_at_commit,
        _vendor_packaged_module_into_app,
    )

    if entry.kind == LockKind.PACKAGED and vendored_dir == ctx.cmake_nsx:
        on_disk_hash = (
            hash_tree(vendored_dir, exclude_names=NSX_TOOLING_AUTOGEN_FILES)
            if vendored_dir.exists()
            else None
        )
    else:
        on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
    if not ctx.force and on_disk_hash == entry.content_hash:
        vendored_paths.add(vendored_dir)
        return 0

    if ctx.frozen:
        raise NSXIntegrityError(
            f"Module '{name}' on-disk content does not match nsx.lock "
            f"({entry.vendored_at}). Refusing to modify under --frozen.",
            module=name,
        )

    if entry.kind == LockKind.PACKAGED:
        _vendor_packaged_module_into_app(ctx.app_dir, name, ctx.registry)
    elif entry.kind == LockKind.GIT:
        # Re-vendor at the exact locked commit (not the branch tip).
        if entry.commit:
            _vendor_git_module_at_commit(
                ctx.app_dir,
                name,
                ctx.registry,
                entry.commit,
                content_hash=entry.content_hash,
            )
        else:
            _update_module_clone(ctx.app_dir, name, ctx.registry)

    # Verify the materialized tree matches what the lock recorded.
    # Mismatch here means upstream content drifted since lock
    # (force-pushed git history, packaged source bumped without a
    # tool_version bump, etc.).
    #
    # Skip the verification for ``cmake/nsx``: that path is
    # unconditionally refreshed by ``_copy_packaged_tree`` at the end of
    # the sync, so its on-disk state mid-loop is transient and any
    # mismatch here would produce a misleading "drifted since lock"
    # warning even when the final state is correct.
    if vendored_dir != ctx.cmake_nsx:
        post_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
        if post_hash != entry.content_hash:
            _log.warning(
                "upstream for '%s' has drifted since lock "
                "(expected %s, got %s); run `nsx lock` to re-record.",
                name,
                entry.content_hash,
                post_hash,
            )
    vendored_paths.add(vendored_dir)
    return 1


def _sync_app_impl_unlocked(
    app_dir: Path,
    *,
    board: str | None = None,
    frozen: bool = False,
    force: bool = False,
) -> None:
    board_key = _board_key_for_app(app_dir, board)
    lock = read_lock(app_dir, board_key)
    if lock is None:
        if frozen:
            raise NSXConfigError(
                f"{lock_path(app_dir)} not found. Run `nsx lock` first (or drop --frozen)."
            )
        # No lock yet — generate one. Unlike the v2 design, this is
        # safe to run on a fresh checkout: ``_build_lock_for_app``
        # hashes the upstream artifact (cloned to a tempdir for git,
        # the wheel resource for packaged, the source path for local),
        # so the recorded content_hash is correct without ``modules/``
        # being populated first.
        _log.info("lock not found; generating from manifest.")
        lock_app_impl(app_dir, board=board, quiet=True)
        lock = read_lock(app_dir, board_key)
        assert lock is not None  # noqa: S101 — invariant guaranteed by lock_app_impl

    nsx_cfg = _load_app_cfg(app_dir)
    app_cfg = AppConfig.from_mapping(nsx_cfg)
    if app_cfg.is_multi_target():
        # Pin the active board so the seeded closure belongs to the board
        # being synced.
        nsx_cfg = _apply_active_target(nsx_cfg, app_cfg.resolve_target(board))
    base_registry = _load_registry()
    # ``modules:`` lists only the app's direct deps; re-seed the full closure
    # and ``module_registry`` overrides (mirroring ``_build_lock_for_app``) so
    # module resolution and the regenerated CMake glue below can find direct
    # deps whose metadata lives in the board family catalog.
    nsx_cfg = expand_profile_seeds(nsx_cfg, base_registry)
    registry = _effective_registry(base_registry, nsx_cfg, app_dir=app_dir)
    validate_app_module_alignment(nsx_cfg, registry)

    # Detect manifest drift — the user edited nsx.yml since the lock was written.
    current_manifest_hash = hash_manifest(app_dir / "nsx.yml")
    if lock.manifest_hash and lock.manifest_hash != current_manifest_hash:
        if frozen:
            raise NSXConfigError(
                "nsx.yml has changed since nsx.lock was written. "
                "Run `nsx lock` to refresh, or drop --frozen."
            )
        _log.warning("nsx.yml has changed since nsx.lock was written; run `nsx lock` to refresh.")

    cmake_nsx = app_dir / "cmake" / "nsx"
    ctx = _SyncContext(
        app_dir=app_dir,
        registry=registry,
        cmake_nsx=cmake_nsx,
        frozen=frozen,
        force=force,
    )

    changed = 0
    # Track resolved vendored directories so two module entries that
    # share one project/path don't each trigger a redundant re-vendor
    # in the same `nsx sync` run.
    vendored_paths: set[Path] = set()

    for name, entry in lock.modules.items():
        vendored_dir = _resolve_vendored_dir(ctx, name, entry)

        # Verify-only kinds (source IS the in-tree directory).
        if entry.kind == LockKind.VENDORED:
            _sync_vendored_entry(ctx, name, entry, vendored_dir, vendored_paths)
            continue
        if entry.kind == LockKind.UNRESOLVED:
            _sync_unresolved_entry(ctx, name, entry, vendored_dir, vendored_paths)
            continue

        # Duplicate-resolution short-circuit (two entries → one path):
        # vendor exactly once per sync. Subsequent entries verify that
        # what's already on disk matches their own expected hash.
        if vendored_dir in vendored_paths:
            _verify_duplicate_path(ctx, name, entry, vendored_dir)
            continue

        if entry.kind == LockKind.LOCAL:
            changed += _sync_local_entry(ctx, name, entry, vendored_dir, vendored_paths)
            continue

        # Packaged / git: fetchable upstream artifacts.
        changed += _sync_fetchable_entry(ctx, name, entry, vendored_dir, vendored_paths)

    # Always refresh the packaged cmake tree and regenerate
    # modules.cmake + modules/.gitignore — these are cheap and keep
    # the build inputs aligned.
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_cmake_nsx_gitignore(app_dir)
    ordered_modules = list(lock.modules)
    _write_app_module_file(app_dir, nsx_cfg, module_names=ordered_modules)
    _write_modules_gitignore_for_module_names(
        app_dir, nsx_cfg, _locked_module_union(app_dir, ordered_modules))

    # Now that ``cmake/nsx`` has been replaced by _copy_packaged_tree,
    # verify any packaged lock entry mapped to that path against its
    # recorded content_hash. Done after the refresh so the warning (if
    # any) reflects the final on-disk state, not the pre-refresh state.
    for name, entry in lock.modules.items():
        if entry.kind != LockKind.PACKAGED:
            continue
        if (app_dir / entry.vendored_at) != cmake_nsx:
            continue
        post_hash = (
            hash_tree(cmake_nsx, exclude_names=NSX_TOOLING_AUTOGEN_FILES)
            if cmake_nsx.exists()
            else None
        )
        if post_hash != entry.content_hash:
            _log.warning(
                "upstream for '%s' has drifted since lock "
                "(expected %s, got %s); run `nsx lock` to re-record.",
                name,
                entry.content_hash,
                post_hash,
            )

    if changed:
        info(f"Synced {changed} module{'s' if changed != 1 else ''} from nsx.lock.")
    else:
        info("All modules already match nsx.lock.")


def update_app_impl(
    app_dir: Path,
    *,
    modules: list[str] | None = None,
) -> None:
    """Re-resolve constraints to current upstream and re-vendor.

    Equivalent to ``nsx lock --update [--module ...]`` followed by
    ``nsx sync``.
    """

    with app_lock(app_dir):
        lock_app_impl(app_dir, update=True, modules=modules)
        sync_app_impl(app_dir)
