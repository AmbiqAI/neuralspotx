"""Lock-file resolution and ``nsx outdated`` reporting."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .._errors import (
    NSXConfigError,
    NSXError,
    NSXModuleError,
    NSXResolutionError,
)
from ..constants import DEFAULT_TOOLCHAIN
from ..file_lock import app_lock
from ..module_registry import (
    _local_module_names,
    _module_names_from_nsx,
    _vendored_module_names,
)
from ..nsx_lock import (
    NSX_TOOLING_AUTOGEN_FILES,
    LockKind,
    NsxLock,
    ResolutionError,
    ResolvedModule,
    hash_git_artifact,
    hash_manifest,
    hash_tree,
    lock_path,
    read_lock,
    resolve_commit,
    resolve_ref,
    utcnow_iso,
    write_lock,
)
from ..project_config import (
    _copy_packaged_tree,
    _effective_registry,
    _load_app_cfg,
    _load_registry,
    _nsx_tool_version,
    _registry_project_entry,
    _write_app_module_file,
    _write_modules_gitignore,
)
from ._common import OutdatedStatus, _log


def _resolved_module_path(
    app_dir: Path,
    module_name: str,
    registry: dict,
) -> Path:
    """Return the on-disk vendored directory for *module_name* in *app_dir*."""

    from ..metadata import registry_entry_for_module
    from ..module_registry import _is_packaged_module
    from ..project_config import _module_clone_dir, _vendored_target_dir

    entry = registry_entry_for_module(registry, module_name)
    if _is_packaged_module(registry, module_name):
        return _vendored_target_dir(app_dir, module_name, entry.metadata)
    return _module_clone_dir(app_dir, entry.project, registry)


def _build_lock_for_app(
    app_dir: Path,
    *,
    previous: NsxLock | None = None,
    write_side_effects: bool = True,
) -> NsxLock:
    """Resolve every module in nsx.yml to a commit + content hash.

    For ``kind=git``: ``content_hash`` is the hash of the upstream
    working tree at the locked commit, computed by cloning into a
    tempdir and stripping ``.git``. This is the cargo/uv-style
    upstream-artifact integrity hash and is independent of whether the
    module is currently materialized under ``modules/<name>/``.

    For ``kind=packaged``: ``content_hash`` is the hash of the packaged
    source tree shipped inside the ``neuralspotx`` Python wheel.

    For ``kind=local`` with a registered ``local_path``:
    ``content_hash`` is the hash of the source path (the upstream).

    For ``kind=local`` without a source path (in-tree, e.g.
    ``nsx module add --local``) and ``kind=vendored``:
    ``content_hash`` is the hash of ``modules/<name>/`` itself \u2014 the
    directory IS the source.

    For ``kind=unresolved``: best-effort hash of whatever is on disk
    (or the previous lock's recorded hash, if nothing is on disk).

    Re-uses entries from *previous* (the existing lock) when the
    constraint is unchanged \u2014 avoids redundant ``git ls-remote`` calls
    *and* avoids re-cloning to recompute the upstream hash.

    When ``write_side_effects`` is False, the build-glue side effects
    (``cmake/nsx/`` copy, ``modules.cmake``, ``modules/.gitignore``)
    are skipped. ``nsx lock --check`` uses this so a read-only check
    truly does not modify the on-disk app.
    """

    from ..metadata import registry_entry_for_module
    from ..module_registry import _is_packaged_module

    nsx_cfg = _load_app_cfg(app_dir)
    base_registry = _load_registry()
    registry = _effective_registry(base_registry, nsx_cfg)
    module_names = _module_names_from_nsx(nsx_cfg)
    local_names = _local_module_names(nsx_cfg)
    vendored_names = _vendored_module_names(nsx_cfg)
    tool_version = _nsx_tool_version()

    if write_side_effects:
        # Regenerate the deterministic side-effects that ``nsx sync`` produces
        # at the end of every run. These are not module trees; they are the
        # build glue (cmake helpers, modules.cmake, modules/.gitignore) that
        # lives outside ``modules/<name>/`` and is therefore not covered by
        # any module's ``content_hash``.
        _copy_packaged_tree("neuralspotx", "cmake", app_dir / "cmake" / "nsx")
        _write_app_module_file(app_dir, nsx_cfg)
        _write_modules_gitignore(app_dir, nsx_cfg)

    lock = NsxLock(
        generated_at=utcnow_iso(),
        nsx_tool_version=tool_version,
        manifest_path="nsx.yml",
        manifest_hash=hash_manifest(app_dir / "nsx.yml"),
        target={
            **(nsx_cfg.get("target") or {}),
            "toolchain": str(nsx_cfg.get("toolchain") or DEFAULT_TOOLCHAIN),
        },
    )

    prev_modules = previous.modules if previous else {}
    # Per-call cache: a single ``nsx lock`` invocation may have multiple
    # modules sharing one (url, commit) pair; clone once.
    git_artifact_hash_cache: dict[tuple[str, str], str] = {}
    # Per-call resolve_ref cache shared by the prefetch pass below and
    # the main loop. Keyed by ``(url, constraint)``.
    resolve_ref_cache: dict[tuple[str, str], tuple[str, str | None]] = {}

    # Parallel prefetch ---------------------------------------------------
    # The main loop below classifies every module, calls ``git ls-remote``
    # to resolve constraints to commits, and then ``git clone``s each
    # ``(url, commit)`` to compute its upstream-artifact hash.  Both
    # steps are I/O-bound and embarrassingly parallel: dispatch them up
    # front via a thread pool and stash results in the per-call caches
    # the main loop already consults.  Falls back to serial execution
    # under ``NSX_RESOLVE_PARALLELISM=1``.
    from .._parallel import parallel_map
    from ..module_registry import _is_packaged_module as _is_pkg

    def _git_resolve_jobs() -> list[tuple[str, str]]:
        jobs: dict[tuple[str, str], None] = {}
        for nm in module_names:
            if nm in vendored_names or nm in local_names:
                continue
            try:
                ent = registry_entry_for_module(registry, nm)
            except (KeyError, ValueError, TypeError) as exc:
                _log.debug("prefetch: skipping %s (registry lookup failed: %s)", nm, exc)
                continue
            if _is_pkg(registry, nm):
                continue
            proj = _registry_project_entry(registry, ent.project)
            if not proj.url:
                continue
            cons = str(ent.revision or "main")
            prev = prev_modules.get(nm)
            if (
                prev
                and prev.kind == LockKind.GIT
                and prev.constraint == cons
                and prev.url == proj.url
                and prev.commit
            ):
                # Re-use of previous SHA short-circuits resolve_ref.
                continue
            jobs[(proj.url, cons)] = None
        return list(jobs.keys())

    _resolve_jobs = _git_resolve_jobs()
    if _resolve_jobs:

        def _safe_resolve_ref(job: tuple[str, str]) -> tuple[str, str | None] | None:
            try:
                return resolve_ref(*job)
            except (
                OSError,
                subprocess.SubprocessError,
                NSXResolutionError,
                ResolutionError,
            ) as exc:
                _log.debug("prefetch: resolve_ref%s failed: %s", job, exc)
                return None

        _results = parallel_map(_safe_resolve_ref, _resolve_jobs)
        for job, result in zip(_resolve_jobs, _results, strict=True):
            if result is not None:
                resolve_ref_cache[job] = result

    def _git_hash_jobs() -> list[tuple[str, str]]:
        jobs: dict[tuple[str, str], None] = {}
        for nm in module_names:
            if nm in vendored_names or nm in local_names:
                continue
            try:
                ent = registry_entry_for_module(registry, nm)
            except (KeyError, ValueError, TypeError) as exc:
                _log.debug("prefetch: skipping %s (registry lookup failed: %s)", nm, exc)
                continue
            if _is_pkg(registry, nm):
                continue
            proj = _registry_project_entry(registry, ent.project)
            if not proj.url:
                continue
            cons = str(ent.revision or "main")
            prev = prev_modules.get(nm)
            if (
                prev
                and prev.kind == LockKind.GIT
                and prev.constraint == cons
                and prev.url == proj.url
                and prev.commit
                and prev.content_hash
            ):
                # The previous lock already has a usable upstream hash;
                # the main loop will reuse it without cloning.
                continue
            cached = resolve_ref_cache.get((proj.url, cons))
            if cached is None:
                continue
            commit_sha, _ = cached
            jobs[(proj.url, commit_sha)] = None
        return list(jobs.keys())

    _hash_jobs = _git_hash_jobs()
    if _hash_jobs:

        def _safe_hash(job: tuple[str, str]) -> str | None:
            try:
                return hash_git_artifact(*job)
            except (
                OSError,
                subprocess.SubprocessError,
                NSXResolutionError,
                ResolutionError,
            ) as exc:
                _log.debug("prefetch: hash_git_artifact%s failed: %s", job, exc)
                return None

        _hashes = parallel_map(_safe_hash, _hash_jobs)
        for job, hashed in zip(_hash_jobs, _hashes, strict=True):
            if hashed is not None:
                git_artifact_hash_cache[job] = hashed
    # End parallel prefetch -----------------------------------------------

    def _resolve_ref_cached(url: str, ref: str) -> tuple[str, str | None]:
        key = (url, ref)
        cached = resolve_ref_cache.get(key)
        if cached is not None:
            return cached
        result = resolve_ref(url, ref)
        resolve_ref_cache[key] = result
        return result

    for name in module_names:
        # Vendored (in-app, source-controlled) modules \u2014 source IS
        # ``modules/<name>/``. No registry, no upstream resolution.
        if name in vendored_names:
            vendored_dir = app_dir / "modules" / name
            if not vendored_dir.exists():
                raise NSXModuleError(
                    f"Module '{name}' declares source: {{ vendored: true }} "
                    f"but {vendored_dir.relative_to(app_dir)}/ is missing. "
                    "Add the module's files (e.g. via `nsx module add --vendored`) "
                    "and re-run `nsx lock`."
                )
            rel = str(vendored_dir.relative_to(app_dir))
            project_key = name  # vendored modules don't belong to a registry project
            for item in nsx_cfg.get("modules", []):
                if isinstance(item, dict) and item.get("name") == name:
                    if isinstance(item.get("project"), str):
                        project_key = item["project"]
                    break
            lock.modules[name] = ResolvedModule(
                project=project_key,
                kind=LockKind.VENDORED,
                constraint="vendored",
                vendored_at=rel,
                content_hash=hash_tree(vendored_dir),
                acquired_at=utcnow_iso(),
            )
            continue

        # Local modules: handled BEFORE the registry lookup, since
        # ``nsx module add --local`` may have written ``local: true``
        # without a corresponding registry override.
        if name in local_names:
            try:
                entry = registry_entry_for_module(registry, name)
                project_key = entry.project
                constraint = str(entry.revision or "local")
                vendored_dir = _resolved_module_path(app_dir, name, registry)
                project_entry = _registry_project_entry(registry, entry.project)
                source_dir = (
                    Path(project_entry.local_path).expanduser().resolve()
                    if project_entry.local_path
                    else None
                )
            except ValueError:
                # No registry entry: in-tree local. Source IS modules/<name>/.
                project_key = name
                constraint = "local"
                vendored_dir = app_dir / "modules" / name
                source_dir = None
            rel = (
                str(vendored_dir.relative_to(app_dir))
                if vendored_dir.is_relative_to(app_dir)
                else str(vendored_dir)
            )
            # Hash the upstream: the registered source path if any,
            # otherwise modules/<name>/ itself (which IS the source for
            # in-tree locals).
            hash_root = source_dir if source_dir is not None else vendored_dir
            if not hash_root.exists():
                raise NSXModuleError(
                    f"Local module '{name}' source '{hash_root}' does not exist; cannot lock."
                )
            lock.modules[name] = ResolvedModule(
                project=project_key,
                kind=LockKind.LOCAL,
                constraint=constraint,
                vendored_at=rel,
                content_hash=hash_tree(hash_root),
                acquired_at=utcnow_iso(),
            )
            continue

        entry = registry_entry_for_module(registry, name)
        constraint = str(entry.revision or "main")

        if _is_packaged_module(registry, name):
            # Source IS the packaged resource directory inside the
            # ``neuralspotx`` wheel. Use the public helper so callers
            # don't depend on a private resolution function and so the
            # path always points at the wheel resource, never an
            # app-local materialized copy.
            from ..module_registry import packaged_module_source_dir

            source_dir = packaged_module_source_dir(name, entry, registry)
            vendored_dir = _resolved_module_path(app_dir, name, registry)
            rel = (
                str(vendored_dir.relative_to(app_dir))
                if vendored_dir.is_relative_to(app_dir)
                else str(vendored_dir)
            )
            lock.modules[name] = ResolvedModule(
                project=entry.project,
                kind=LockKind.PACKAGED,
                constraint="packaged",
                vendored_at=rel,
                content_hash=hash_tree(source_dir, exclude_names=NSX_TOOLING_AUTOGEN_FILES),
                acquired_at=utcnow_iso(),
                tool_version=tool_version,
            )
            continue

        # Git-hosted module \u2014 resolve constraint to a commit SHA via ls-remote.
        project_entry = _registry_project_entry(registry, entry.project)
        url = project_entry.url
        if not url:
            # Project has no upstream URL but does declare a local source
            # path (e.g. registered via `nsx module register
            # --project-local-path`). Treat it like a local mirror: hash
            # the source path (the upstream) and skip ls-remote.
            if project_entry.local_path:
                vendored_dir = _resolved_module_path(app_dir, name, registry)
                rel = (
                    str(vendored_dir.relative_to(app_dir))
                    if vendored_dir.is_relative_to(app_dir)
                    else str(vendored_dir)
                )
                source_dir = Path(project_entry.local_path).expanduser().resolve()
                if not source_dir.exists():
                    raise NSXResolutionError(
                        f"Local project '{entry.project}' source '{source_dir}' does "
                        "not exist; cannot lock."
                    )
                lock.modules[name] = ResolvedModule(
                    project=entry.project,
                    kind=LockKind.LOCAL,
                    constraint=constraint,
                    vendored_at=rel,
                    content_hash=hash_tree(source_dir),
                    acquired_at=utcnow_iso(),
                )
                continue
            raise NSXResolutionError(
                f"Module '{name}' project '{entry.project}' has no URL in registry; cannot lock."
            )

        previous_entry = prev_modules.get(name)
        commit: str | None
        tag: str | None
        if (
            previous_entry
            and previous_entry.kind == LockKind.GIT
            and previous_entry.constraint == constraint
            and previous_entry.url == url
            and previous_entry.commit
        ):
            # Re-use the previously resolved SHA \u2014 ``nsx update`` is the
            # explicit way to re-resolve.
            commit = previous_entry.commit
            tag = previous_entry.tag
        else:
            try:
                commit, matched = _resolve_ref_cached(url, constraint)
            except ResolutionError as exc:
                # Upstream not reachable. Degrade to a content-only lock
                # entry. We cannot compute an upstream-artifact hash
                # without the remote, so fall back to whatever is on
                # disk now (or the previous lock's recorded hash).
                _log.warning(
                    "could not resolve %s @ %s on %s (%s); recording content-only lock entry.",
                    name,
                    constraint,
                    url,
                    exc,
                )
                vendored_dir = _resolved_module_path(app_dir, name, registry)
                rel = (
                    str(vendored_dir.relative_to(app_dir))
                    if vendored_dir.is_relative_to(app_dir)
                    else str(vendored_dir)
                )
                if vendored_dir.exists():
                    fallback_hash = hash_tree(vendored_dir)
                elif previous_entry and previous_entry.content_hash:
                    fallback_hash = previous_entry.content_hash
                else:
                    fallback_hash = hash_tree(vendored_dir)  # empty-tree sha
                lock.modules[name] = ResolvedModule(
                    project=entry.project,
                    kind=LockKind.UNRESOLVED,
                    constraint=constraint,
                    vendored_at=rel,
                    content_hash=fallback_hash,
                    acquired_at=utcnow_iso(),
                    url=url,
                    tag=None,
                    commit=None,
                )
                continue
            tag = constraint if matched == "tag" else None

        vendored_dir = _resolved_module_path(app_dir, name, registry)
        rel = (
            str(vendored_dir.relative_to(app_dir))
            if vendored_dir.is_relative_to(app_dir)
            else str(vendored_dir)
        )

        # Upstream-artifact hash: clone at the resolved commit, hash the
        # working tree (sans .git). Re-use the previous lock's hash when
        # the (url, commit) pair is unchanged \u2014 the upstream artifact
        # is content-addressed by the commit SHA, so a re-clone would
        # produce the same hash.
        cache_key = (url, commit)
        if (
            previous_entry
            and previous_entry.kind == LockKind.GIT
            and previous_entry.url == url
            and previous_entry.commit == commit
            and previous_entry.content_hash
        ):
            content_hash = previous_entry.content_hash
            git_artifact_hash_cache.setdefault(cache_key, content_hash)
        elif cache_key in git_artifact_hash_cache:
            content_hash = git_artifact_hash_cache[cache_key]
        else:
            try:
                content_hash = hash_git_artifact(url, commit)
            except Exception as exc:  # noqa: BLE001 \u2014 surface as actionable error
                raise NSXResolutionError(
                    f"Failed to compute upstream hash for '{name}' ({url} @ {commit}): {exc}"
                ) from exc
            git_artifact_hash_cache[cache_key] = content_hash

        lock.modules[name] = ResolvedModule(
            project=entry.project,
            kind=LockKind.GIT,
            constraint=constraint,
            vendored_at=rel,
            content_hash=content_hash,
            acquired_at=utcnow_iso(),
            url=url,
            tag=tag,
            commit=commit,
        )

    return lock


def lock_app_impl(
    app_dir: Path,
    *,
    update: bool = False,
    modules: list[str] | None = None,
    check: bool = False,
    quiet: bool = False,
) -> NsxLock:
    """Resolve and write ``nsx.lock`` for *app_dir*.

    Args:
        update: When True, re-resolve every module's constraint to its
            current upstream HEAD/tag (equivalent to ``nsx update``).
        modules: When given alongside ``update``, only re-resolve these.
        check: Read-only mode. Resolve as usual but, instead of writing,
            compare against the on-disk ``nsx.lock`` and raise
            :class:`NSXError` when they would differ. Useful in CI to
            assert that ``nsx.lock`` is up to date with ``nsx.yml``.
        quiet: Suppress the post-write "Wrote ... / modules: ..."
            summary print. Useful when ``nsx lock`` is invoked
            implicitly by another command (e.g. the lock-missing path
            in ``sync_app_impl``) and the surrounding command has
            already printed its own summary.

    Returns:
        The resolved :class:`~neuralspotx.nsx_lock.NsxLock`. The
        filesystem path to the (would-be) ``nsx.lock`` is available
        on ``lock.path``.
    """

    # ``--check`` is read-only (no writes to ``nsx.lock`` or build glue),
    # so it does not need the per-app advisory lock and CI can verify
    # multiple apps in parallel without contention.
    if check:
        return _lock_app_impl_unlocked(
            app_dir, update=update, modules=modules, check=True, quiet=quiet
        )
    with app_lock(app_dir):
        return _lock_app_impl_unlocked(
            app_dir, update=update, modules=modules, check=False, quiet=quiet
        )


def _lock_app_impl_unlocked(
    app_dir: Path,
    *,
    update: bool = False,
    modules: list[str] | None = None,
    check: bool = False,
    quiet: bool = False,
) -> NsxLock:
    previous = read_lock(app_dir, allow_legacy=True)
    on_disk_lock = previous  # capture before update-mutation

    if update:
        # Force fresh resolution — clear the persistent resolve-ref cache
        # so ``git ls-remote`` results are re-fetched from the network.
        from .. import _resolve_cache

        _resolve_cache.invalidate_all()

        if previous and modules:
            # Drop the named entries from `previous` so they get re-resolved.
            kept = {n: e for n, e in previous.modules.items() if n not in set(modules)}
            previous = NsxLock(
                schema_version=previous.schema_version,
                generated_at=previous.generated_at,
                nsx_tool_version=previous.nsx_tool_version,
                manifest_path=previous.manifest_path,
                manifest_hash=previous.manifest_hash,
                target=previous.target,
                modules=kept,
            )
        elif previous and not modules:
            previous = None  # full refresh

    lock = _build_lock_for_app(app_dir, previous=previous, write_side_effects=not check)
    lock_file = lock_path(app_dir)

    if check:
        diff = _diff_locks(on_disk_lock, lock)
        rel = (
            lock_file.relative_to(app_dir.parent)
            if lock_file.is_relative_to(app_dir.parent)
            else lock_file
        )
        if not diff:
            print(f"{rel} is up to date.")
            lock.path = lock_file
            return lock
        print(f"{rel} is OUT OF DATE:")
        for line in diff:
            print(f"  {line}")
        print("Run `nsx lock` to refresh.")
        raise NSXError(1)

    path = write_lock(app_dir, lock)
    # ``write_lock`` already stamps ``lock.path`` for us.
    if quiet:
        return lock
    print(
        f"Wrote {path.relative_to(app_dir.parent) if path.is_relative_to(app_dir.parent) else path}"
    )
    n_git = sum(1 for m in lock.modules.values() if m.kind == LockKind.GIT)
    n_pkg = sum(1 for m in lock.modules.values() if m.kind == LockKind.PACKAGED)
    n_loc = sum(1 for m in lock.modules.values() if m.kind == LockKind.LOCAL)
    n_ven = sum(1 for m in lock.modules.values() if m.kind == LockKind.VENDORED)
    n_unres = sum(1 for m in lock.modules.values() if m.kind == LockKind.UNRESOLVED)
    parts = [f"{n_git} git", f"{n_pkg} packaged", f"{n_loc} local"]
    if n_ven:
        parts.append(f"{n_ven} vendored")
    if n_unres:
        parts.append(f"{n_unres} unresolved (upstream unreachable)")
    print(f"  modules: {len(lock.modules)} ({', '.join(parts)})")
    return lock


def _diff_locks(previous: NsxLock | None, fresh: NsxLock) -> list[str]:
    """Return a human-readable list of differences relevant to drift detection.

    Compares only the resolution-affecting fields (manifest hash, kind,
    constraint, commit, content_hash) — not timestamps or the tool
    version, which legitimately move on every regenerate.
    """

    if previous is None:
        return [f"no nsx.lock present (would create {len(fresh.modules)} entries)"]

    diffs: list[str] = []
    if previous.manifest_hash != fresh.manifest_hash:
        diffs.append(
            f"manifest hash: {previous.manifest_hash[:14]}\u2026 -> {fresh.manifest_hash[:14]}\u2026"
        )

    prev_names = set(previous.modules)
    fresh_names = set(fresh.modules)
    for name in sorted(fresh_names - prev_names):
        diffs.append(f"+ {name}")
    for name in sorted(prev_names - fresh_names):
        diffs.append(f"- {name}")
    for name in sorted(prev_names & fresh_names):
        a = previous.modules[name]
        b = fresh.modules[name]
        if a.kind != b.kind:
            diffs.append(f"~ {name}: kind {a.kind} -> {b.kind}")
        if a.constraint != b.constraint:
            diffs.append(f"~ {name}: constraint {a.constraint} -> {b.constraint}")
        if (a.commit or "") != (b.commit or ""):
            ac = (a.commit or "-")[:10]
            bc = (b.commit or "-")[:10]
            diffs.append(f"~ {name}: commit {ac} -> {bc}")
        if a.content_hash != b.content_hash:
            diffs.append(f"~ {name}: content hash differs")
    return diffs


def outdated_app_impl(app_dir: Path, *, as_json: bool = False) -> int:
    """Report git modules whose locked commit lags behind the upstream constraint.

    Returns the number of outdated modules so callers (e.g. CI) can use
    the exit code as a signal.
    """

    lock = read_lock(app_dir)
    if lock is None:
        raise NSXConfigError(f"{app_dir / 'nsx.lock'} not found. Run `nsx lock` first.")

    rows: list[tuple[str, str, str, str, str]] = []  # name, constraint, locked, upstream, status
    full_rows: list[dict[str, str]] = []
    skipped: list[tuple[str, str]] = []

    # Parallel prefetch of upstream commits --------------------------------
    # ``resolve_commit`` is one ``git ls-remote`` per call; for an app
    # with many git-hosted modules this is the dominant cost of
    # ``nsx outdated``.  Dispatch the unique ``(url, ref)`` pairs in
    # parallel and stash the results (or the raised exception) in a
    # dict the serial loop below consults.
    from .._parallel import parallel_map

    candidates = [
        (name, entry)
        for name, entry in sorted(lock.modules.items())
        if entry.kind == LockKind.GIT and entry.url
    ]
    upstream_jobs: dict[tuple[str, str], None] = {}
    for _name, entry in candidates:
        upstream_jobs[(entry.url or "", entry.tag or entry.constraint)] = None
    upstream_keys = list(upstream_jobs.keys())

    def _safe_resolve(job: tuple[str, str]) -> tuple[str | None, str | None]:
        try:
            return resolve_commit(job[0], job[1]), None
        except ResolutionError as exc:  # noqa: BLE001
            return None, str(exc)

    upstream_results: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    if upstream_keys:
        results = parallel_map(_safe_resolve, upstream_keys)
        upstream_results = dict(zip(upstream_keys, results, strict=True))

    for name, entry in sorted(lock.modules.items()):
        if entry.kind != LockKind.GIT:
            continue
        if not entry.url:
            skipped.append((name, "no url"))
            continue
        sha, err = upstream_results.get(
            (entry.url, entry.tag or entry.constraint), (None, "unresolved")
        )
        if sha is None:
            skipped.append((name, err or "unresolved"))
            continue
        upstream = sha
        locked = (entry.commit or "").lower()
        if upstream.lower() == locked:
            status = OutdatedStatus.UP_TO_DATE
        else:
            status = OutdatedStatus.OUTDATED
        rows.append((name, entry.constraint, locked[:10], upstream[:10], status))
        full_rows.append({
            "module": name,
            "constraint": entry.constraint,
            "locked": locked,
            "upstream": upstream.lower(),
            "status": status,
            "url": entry.url or "",
        })

    outdated = [r for r in rows if r[4] == OutdatedStatus.OUTDATED]

    if as_json:
        import json

        payload = {
            "checked": full_rows,
            "skipped": [{"module": n, "reason": r} for n, r in skipped],
            "outdated_count": len(outdated),
        }
        print(json.dumps(payload, indent=2))
        return len(outdated)

    if not rows and not skipped:
        print("No git modules to check.")
        return 0

    name_w = max((len(r[0]) for r in rows), default=4)
    cons_w = max((len(r[1]) for r in rows), default=10)
    header = f"{'module'.ljust(name_w)}  {'constraint'.ljust(cons_w)}  {'locked'.ljust(10)}  {'upstream'.ljust(10)}  status"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r[0].ljust(name_w)}  {r[1].ljust(cons_w)}  {r[2].ljust(10)}  {r[3].ljust(10)}  {r[4]}"
        )

    if skipped:
        print()
        for name, reason in skipped:
            print(f"skipped: {name} ({reason})")

    print()
    if outdated:
        names = ", ".join(r[0] for r in outdated)
        print(f"{len(outdated)} outdated: {names}")
        print("Run `nsx update` (all) or `nsx update --module <name>` to refresh.")
    else:
        print("All git modules are up-to-date with their constraints.")
    return len(outdated)
