"""Read selected manifests from the same source bytes that produced the receipt."""

from collections import defaultdict
from pathlib import Path

import yaml

from .._errors import NSXConfigError
from ..models._module_license import parse_module_licenses
from ..nsx_lock import NSX_TOOLING_AUTOGEN_FILES, LockKind, NsxLock, hash_tree


def locked_module_licenses(app_dir: Path, lock: NsxLock) -> dict[str, dict[str, str | None]]:
    app_dir = app_dir.resolve()
    projects: dict[tuple[Path, frozenset[str]], list[tuple[str, Path, str]]] = defaultdict(list)
    for name, entry in lock.modules.items():
        if not entry.manifest_path or not entry.vendored_at or not entry.content_hash:
            continue
        root = (app_dir / entry.vendored_at).resolve()
        if root == app_dir or not root.is_relative_to(app_dir) or not root.is_dir():
            continue
        excluded = (
            NSX_TOOLING_AUTOGEN_FILES
            if entry.kind == LockKind.PACKAGED and root == app_dir / "cmake" / "nsx"
            else frozenset()
        )
        projects[root, excluded].append((name, Path(entry.manifest_path), entry.content_hash))

    licenses: dict[str, dict[str, str | None]] = {}
    for (root, excluded), entries in projects.items():
        manifests: dict[Path, bytes | None] = {path: None for _, path, _ in entries}
        try:
            digest = hash_tree(root, exclude_names=excluded, module_manifests=manifests)
        except OSError:
            continue
        for name, path, expected in entries:
            content = manifests[path]
            if expected != digest or content is None:
                continue
            try:
                data = yaml.safe_load(content)
            except (ValueError, yaml.YAMLError):
                continue
            if (
                not isinstance(data, dict)
                or data.get("schema_version") != 1
                or "licenses" not in data
            ):
                continue
            module = data.get("module")
            if not isinstance(module, dict) or module.get("name") != name:
                continue
            try:
                scopes = parse_module_licenses(data["licenses"], str(root / path))
            except ValueError as exc:
                raise NSXConfigError(str(exc), field="licenses") from exc
            licenses[name] = {
                (path.parent / scope).as_posix(): expression for scope, expression in scopes.items()
            }
    return licenses
