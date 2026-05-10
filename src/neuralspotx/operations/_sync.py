"""Module sync — make ``modules/`` match ``nsx.lock``."""

from __future__ import annotations

from pathlib import Path

from .._errors import NSXConfigError, NSXModuleError
from ..file_lock import app_lock
from ..module_registry import _update_module_clone
from ..nsx_lock import (
    NSX_TOOLING_AUTOGEN_FILES,
    LockKind,
    hash_manifest,
    hash_tree,
    read_lock,
)
from ..project_config import (
    _copy_packaged_tree,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _registry_project_entry,
    _write_app_module_file,
    _write_modules_gitignore,
)
from ._lock import _resolved_module_path, lock_app_impl


def _ensure_app_modules(app_dir: Path) -> None:
    """Ensure all modules declared in nsx.yml are present on disk.

    This is called during ``nsx configure`` so that a freshly-cloned app
    (whose registry modules are gitignored) can be configured without
    a separate ``nsx module add`` or ``nsx module update`` step.

    The lock file is the single source of truth: ``sync_app_impl``
    handles both the lock-present and lock-missing cases. When the
    lock is missing, it creates ``nsx.lock`` and then vendors modules
    according to the resolved lock; it does not rewrite the lock
    after vendoring (``content_hash`` is the upstream-artifact hash,
    so it is correct from the start under v3).
    """

    sync_app_impl(app_dir)


def sync_app_impl(
    app_dir: Path,
    *,
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
        _sync_app_impl_unlocked(app_dir, frozen=frozen, force=force)


def _sync_app_impl_unlocked(
    app_dir: Path,
    *,
    frozen: bool = False,
    force: bool = False,
) -> None:
    from ..module_registry import (
        _vendor_git_module_at_commit,
        _vendor_local_module_into_app,
        _vendor_packaged_module_into_app,
    )

    lock = read_lock(app_dir)
    if lock is None:
        if frozen:
            raise NSXConfigError(
                f"{app_dir / 'nsx.lock'} not found. Run `nsx lock` first (or drop --frozen)."
            )
        # No lock yet — generate one. Unlike the v2 design, this is
        # safe to run on a fresh checkout: ``_build_lock_for_app``
        # hashes the upstream artifact (cloned to a tempdir for git,
        # the wheel resource for packaged, the source path for local),
        # so the recorded content_hash is correct without ``modules/``
        # being populated first.
        print("note: nsx.lock not found; generating from manifest.")
        lock_app_impl(app_dir, quiet=True)
        lock = read_lock(app_dir)
        assert lock is not None  # noqa: S101 — invariant guaranteed by lock_app_impl

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)

    # Detect manifest drift — the user edited nsx.yml since the lock was written.
    current_manifest_hash = hash_manifest(app_dir / "nsx.yml")
    if lock.manifest_hash and lock.manifest_hash != current_manifest_hash:
        if frozen:
            raise NSXConfigError(
                "nsx.yml has changed since nsx.lock was written. "
                "Run `nsx lock` to refresh, or drop --frozen."
            )
        print("warning: nsx.yml has changed since nsx.lock was written; run `nsx lock` to refresh.")

    changed = 0
    # Track resolved vendored directories so two module entries that
    # share one project/path don't each trigger a redundant re-vendor
    # in the same `nsx sync` run.
    vendored_paths: set[Path] = set()

    for name, entry in lock.modules.items():
        # Resolve the destination directory. Vendored / unresolved
        # entries don't necessarily have a registry entry; trust the
        # path recorded in the lock for those. Local entries may also
        # be locked without a registry entry (e.g. ``nsx module add
        # --local`` writes ``local: true`` without an override) — fall
        # back to the lock-recorded path in that case so
        # ``_resolved_module_path()`` doesn't raise.
        if entry.kind in (LockKind.VENDORED, LockKind.UNRESOLVED):
            vendored_dir = app_dir / entry.vendored_at
        elif entry.kind == LockKind.LOCAL:
            try:
                vendored_dir = _resolved_module_path(app_dir, name, registry)
            except ValueError:
                # ``registry_entry_for_module`` raises ``ValueError``
                # when the module isn't in the registry (e.g. ``nsx
                # module add --local`` writes ``local: true`` without
                # an override). Trust the path recorded in the lock.
                vendored_dir = app_dir / entry.vendored_at
        else:
            vendored_dir = _resolved_module_path(app_dir, name, registry)

        # ----- vendored: source IS modules/<name>/; verify only -----
        if entry.kind == LockKind.VENDORED:
            if not vendored_dir.exists():
                # Vendored modules are not fetchable -- the source IS
                # the in-tree directory. A missing path means the
                # user deleted committed content; sync cannot repair
                # it without a checkout/restore.
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
                if frozen:
                    raise NSXModuleError(msg)
                print(f"warning: {msg}")
            vendored_paths.add(vendored_dir)
            continue

        # ----- unresolved: upstream unreachable; verify only -----
        if entry.kind == LockKind.UNRESOLVED:
            if not vendored_dir.exists():
                # Upstream is unreachable by definition for unresolved
                # entries; we cannot repair a missing tree from any
                # source.
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
                if frozen:
                    raise NSXModuleError(msg)
                print(f"warning: {msg}")
            vendored_paths.add(vendored_dir)
            continue

        # Duplicate-resolution short-circuit (two entries → one path):
        # vendor exactly once per sync. Subsequent entries verify that
        # what's already on disk matches their own expected hash.
        if vendored_dir in vendored_paths:
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
                if frozen:
                    raise NSXModuleError(msg)
                print(f"warning: {msg}")
            continue

        # ----- local: upstream is a source path or modules/<name>/ -----
        if entry.kind == LockKind.LOCAL:
            try:
                project_entry = _registry_project_entry(registry, entry.project)
            except (ValueError, KeyError, TypeError):
                project_entry = None

            if project_entry is not None and project_entry.local_path:
                # ``content_hash`` is the hash of the upstream source
                # directory (``project_entry.local_path``), not the
                # vendored mirror. Compare against the live source
                # tree to detect upstream drift; compare on-disk vs
                # source to decide whether the mirror needs an
                # update. (Bug fix: previously we compared
                # ``hash_tree(vendored_dir) == entry.content_hash``,
                # which silently skipped re-mirroring when source had
                # drifted to a hash equal to the lock's old value.)
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
                    if frozen:
                        raise NSXModuleError(msg)
                    print(f"warning: {msg}")

                # Mirror is already in sync with current source: skip.
                if not force and on_disk_hash == source_hash:
                    vendored_paths.add(vendored_dir)
                    continue

                if frozen:
                    raise NSXModuleError(
                        f"Local module '{name}' mirror at {entry.vendored_at} "
                        f"does not match source {source_dir}. Refusing under "
                        "--frozen."
                    )
                _vendor_local_module_into_app(app_dir, name, registry)
                vendored_paths.add(vendored_dir)
                changed += 1
                continue

            # In-tree local (no source path): source IS modules/<name>/.
            # Verify only, like vendored.
            on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
            if on_disk_hash != entry.content_hash:
                msg = (
                    f"Local module '{name}' content drifted from lock "
                    f"({entry.vendored_at}). Run `nsx lock` to re-record, "
                    "or revert the changes."
                )
                if frozen:
                    raise NSXModuleError(msg)
                print(f"warning: {msg}")
            vendored_paths.add(vendored_dir)
            continue

        # ----- packaged / git: fetchable upstream artifacts -----
        on_disk_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
        if not force and on_disk_hash == entry.content_hash:
            vendored_paths.add(vendored_dir)
            continue

        if frozen:
            raise NSXModuleError(
                f"Module '{name}' on-disk content does not match nsx.lock "
                f"({entry.vendored_at}). Refusing to modify under --frozen."
            )

        if entry.kind == LockKind.PACKAGED:
            _vendor_packaged_module_into_app(app_dir, name, registry)
        elif entry.kind == LockKind.GIT:
            # Re-vendor at the exact locked commit (not the branch tip).
            if entry.commit:
                _vendor_git_module_at_commit(
                    app_dir,
                    name,
                    registry,
                    entry.commit,
                    content_hash=entry.content_hash,
                )
            else:
                _update_module_clone(app_dir, name, registry)

        # Verify the materialized tree matches what the lock recorded.
        # Mismatch here means upstream content drifted since lock
        # (force-pushed git history, packaged source bumped without a
        # tool_version bump, etc.).
        #
        # Skip the verification for ``cmake/nsx``: that path is
        # unconditionally refreshed by ``_copy_packaged_tree`` at the
        # end of this function, so its on-disk state mid-loop is
        # transient and any mismatch here would produce a misleading
        # "drifted since lock" warning even when the final state is
        # correct.
        if vendored_dir != app_dir / "cmake" / "nsx":
            post_hash = hash_tree(vendored_dir) if vendored_dir.exists() else None
            if post_hash != entry.content_hash:
                print(
                    f"warning: upstream for '{name}' has drifted since lock "
                    f"(expected {entry.content_hash}, got {post_hash}); "
                    "run `nsx lock` to re-record."
                )
        vendored_paths.add(vendored_dir)
        changed += 1

    # Always refresh the packaged cmake tree and regenerate
    # modules.cmake + modules/.gitignore — these are cheap and keep
    # the build inputs aligned.
    _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
    _write_app_module_file(app_dir, nsx_cfg)
    _write_modules_gitignore(app_dir, nsx_cfg)

    # Now that ``cmake/nsx`` has been replaced by _copy_packaged_tree,
    # verify any packaged lock entry mapped to that path against its
    # recorded content_hash. Done after the refresh so the warning (if
    # any) reflects the final on-disk state, not the pre-refresh state.
    cmake_nsx = app_dir / "cmake" / "nsx"
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
            print(
                f"warning: upstream for '{name}' has drifted since lock "
                f"(expected {entry.content_hash}, got {post_hash}); "
                "run `nsx lock` to re-record."
            )

    if changed:
        print(f"Synced {changed} module{'s' if changed != 1 else ''} from nsx.lock.")
    else:
        print("All modules already match nsx.lock.")


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
