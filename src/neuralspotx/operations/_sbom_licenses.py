"""Read scoped declarations from the same source bytes that produced the receipt."""

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from .._errors import NSXConfigError
from ..models._module_license import parse_module_licenses
from ..nsx_lock import NSX_TOOLING_AUTOGEN_FILES, LockKind, NsxLock, hash_tree


def locked_module_licenses(app_dir: Path, lock: NsxLock) -> dict[str, dict[str, str | None]]:
    app_dir = app_dir.resolve()
    projects: dict[tuple[Path, frozenset[str]], dict[str, str]] = defaultdict(dict)
    for name, entry in lock.modules.items():
        if not entry.vendored_at or not entry.content_hash:
            continue
        root = (app_dir / entry.vendored_at).resolve()
        if root == app_dir or not root.is_relative_to(app_dir) or not root.is_dir():
            continue
        excluded = (
            NSX_TOOLING_AUTOGEN_FILES
            if entry.kind == LockKind.PACKAGED and root == app_dir / "cmake" / "nsx"
            else frozenset()
        )
        projects[root, excluded][name] = entry.content_hash

    licenses: dict[str, dict[str, str | None]] = {}
    for (root, excluded), expected in projects.items():
        manifests: dict[Path, bytes] = {}
        try:
            digest = hash_tree(root, exclude_names=excluded, module_manifests=manifests)
        except OSError:
            continue
        if digest not in expected.values():
            continue
        candidates: dict[str, list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
        for path, content in manifests.items():
            try:
                data = yaml.safe_load(content)
            except (ValueError, yaml.YAMLError):
                continue
            if not isinstance(data, dict) or not isinstance(module := data.get("module"), dict):
                continue
            name = module.get("name")
            if isinstance(name, str) and expected.get(name) == digest:
                candidates[name].append((path, data))

        for name, matches in candidates.items():
            # The receipt identifies a tree and module name. Two manifests for
            # that name leave the selection ambiguous.
            if len(matches) != 1:
                continue
            path, data = matches[0]
            if data.get("schema_version") != 1 or "licenses" not in data:
                continue
            try:
                scopes = parse_module_licenses(data["licenses"], str(root / path))
            except ValueError as exc:
                raise NSXConfigError(str(exc), field="licenses") from exc
            licenses[name] = {
                (path.parent / scope).as_posix(): expression for scope, expression in scopes.items()
            }
    return licenses
