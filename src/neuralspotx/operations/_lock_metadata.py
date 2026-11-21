"""Git sources used while discovering a writable lock's dependency graph."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .._errors import NSXConfigError
from ..constants import PACKAGED_PROJECT_NAME
from ..models import ProjectEntry
from ..module_registry._vendoring import _ensure_module_cloned
from ..nsx_lock import LockKind, NsxLock
from ..nsx_lock._resolution import _looks_like_full_sha
from ..project_config import (
    RegistryAuthorship,
    _metadata_in_checkout,
    _metadata_path_relative_to_project,
    _module_clone_dir,
    _registry_project_entry,
)


def independently_locked_projects(
    sections: dict[str, NsxLock], selected: frozenset[str]
) -> frozenset[str]:
    """Projects for which one shared app-local checkout cannot represent every board."""
    pins: dict[str, set[tuple[str | None, str | None, bool]]] = {}
    for section in sections.values():
        refresh = {
            row.project
            for name, row in section.modules.items()
            if name in selected and row.kind == LockKind.GIT
        }
        for row in section.modules.values():
            if row.kind == LockKind.GIT:
                pins.setdefault(row.project, set()).add((
                    row.url,
                    row.commit,
                    row.project in refresh,
                ))
    return frozenset(project for project, identities in pins.items() if len(identities) > 1)


# Only directories created during this lock operation are tracked. A checkout
# present before the call retains its normal app-local metadata precedence.
AcquiredSources = dict[Path, tuple[str | None, frozenset[str]]]


@contextmanager
def _separate_new_checkouts(
    app_dir: Path,
    registry: dict,
    modules: dict,
    acquired: AcquiredSources | None,
) -> Iterator[set[str]]:
    separate: set[str] = set()
    pending: AcquiredSources = {}
    if acquired is not None:
        revisions: dict[str, set[str]] = {}
        for module in modules.values():
            revisions.setdefault(module["project"], set()).add(module.get("revision") or "main")
        for name, refs in revisions.items():
            project = _registry_project_entry(registry, name)
            if project.local_path or not project.url:
                continue
            path = _module_clone_dir(app_dir, name, registry).resolve()
            source = (project.url, frozenset(refs))
            if path in acquired:
                if acquired[path] != source or len(refs) != 1:
                    separate.add(name)
            elif not path.exists():
                if path in pending and pending[path] != source:
                    separate.add(name)
                else:
                    pending[path] = source
    yield separate
    if acquired is not None:
        acquired.update((path, source) for path, source in pending.items() if path.is_dir())


@contextmanager
def discovery_registry(
    app_dir: Path,
    registry: dict[str, Any],
    previous: NsxLock | None,
    authorship: RegistryAuthorship,
    refresh: set[str],
    isolated: frozenset[str],
    acquired: AcquiredSources | None,
    manifests: dict[str, str],
    *,
    read_only: bool,
) -> Iterator[tuple[dict[str, Any], Callable[[str], None] | None]]:
    """Choose revisions for acquisition without changing the constraints recorded in the lock."""
    if previous is None and not isolated and acquired is None:
        yield registry, None
        return
    modules = dict(registry["modules"])
    projects = dict(registry["projects"])
    private = set(isolated)
    if previous:
        for name, row in previous.modules.items():
            module = modules.get(name)
            if not module or row.kind != LockKind.GIT or not row.url or not row.commit:
                continue
            if not _looks_like_full_sha(row.commit):
                continue
            project = _registry_project_entry(registry, module["project"])
            if project.local_path:
                continue
            moved = row.project != project.name
            new_url = row.url != project.url
            new_ref = row.constraint != (module.get("revision") or "main")
            if (
                (moved and name in authorship.module_projects)
                or (new_url and project.name in authorship.project_urls)
                or (new_ref and name in authorship.module_revisions)
            ):
                continue
            if (moved or new_url or new_ref) and project.name != PACKAGED_PROJECT_NAME:
                # A check of new defaults can report identity drift without
                # installing the new artifact. A writable retry must validate
                # the selected revision without consuming an old checkout.
                if not read_only or project.name not in refresh:
                    private.add(project.name)
            if project.name in refresh:
                continue
            if moved or new_url:
                # A consolidated project can contain modules from different old
                # repositories. Address each original artifact independently.
                key = f"qualified:{name}"
                while key in projects:
                    key += ":"
                projects[key] = {"url": row.url, "path": row.vendored_at}
                private.add(key)
                modules[name] = {
                    **module,
                    "project": key,
                    "revision": row.commit,
                    "metadata": row.manifest_path or module["metadata"],
                }
            else:
                modules[name] = {**module, "revision": row.commit}

    registry = {**registry, "projects": projects}
    with _separate_new_checkouts(app_dir, registry, modules, acquired) as different:
        with _board_sources(
            app_dir,
            registry,
            modules,
            frozenset(private | different),
            manifests,
            read_only=read_only,
        ) as view:
            yield view


@contextmanager
def _board_sources(
    app_dir: Path,
    registry: dict,
    modules: dict,
    isolated: frozenset[str],
    manifests: dict[str, str],
    *,
    read_only: bool,
) -> Iterator[tuple[dict[str, Any], Callable[[str], None] | None]]:
    if not isolated:
        yield {**registry, "modules": modules}, None
        return

    # Each board needs its own view of these projects, even when a preceding
    # board has already populated the shared modules/ directory. Acquisition
    # remains lazy: the traversal fetches only projects it actually reaches.
    projects = dict(registry["projects"])
    temporary_modules: set[str] = set()
    ambiguous: dict[str, tuple[Path, ProjectEntry, Path]] = {}
    with tempfile.TemporaryDirectory(prefix="nsx-lock-metadata-") as temporary:
        for index, project_name in enumerate(sorted(isolated & projects.keys())):
            project = _registry_project_entry(registry, project_name)
            if project.local_path or not project.url:
                continue
            root = Path(temporary) / str(index)
            projects[project_name] = {**projects[project_name], "path": str(root)}
            for name, module in modules.items():
                if module["project"] != project_name:
                    continue
                temporary_modules.add(name)
                metadata = Path(module["metadata"])
                if metadata.is_absolute():
                    try:
                        relative = metadata.relative_to(
                            _module_clone_dir(app_dir, project_name, registry)
                        )
                    except ValueError as exc:
                        raise NSXConfigError(
                            f"Module '{name}' metadata must be inside its Git project."
                        ) from exc
                else:
                    relative = _metadata_path_relative_to_project(metadata, project.checkout_path)
                    if project.path is None and relative != metadata:
                        ambiguous[name] = (metadata, project, root)
                if ".." in relative.parts:
                    raise NSXConfigError(f"Module '{name}' metadata escapes its Git project.")
                modules[name] = {**module, "metadata": str(root / relative)}

        view = {**registry, "modules": modules, "projects": projects}

        def prepare_metadata(name: str) -> None:
            # Read-only checks can populate the private checkout for this board.
            # Other sources retain ordinary check behavior inside the app.
            if read_only and name in temporary_modules:
                _ensure_module_cloned(app_dir, name, view)
            # A default checkout prefix can also be a real directory *inside*
            # the repo. Disambiguate only after DFS has fetched this project.
            if name in ambiguous:
                selector, project, root = ambiguous[name]
                relative = _metadata_in_checkout(selector, project, root)
                modules[name]["metadata"] = str(root / relative)
                manifests[name] = relative.as_posix()

        yield view, prepare_metadata if ambiguous or (read_only and temporary_modules) else None
