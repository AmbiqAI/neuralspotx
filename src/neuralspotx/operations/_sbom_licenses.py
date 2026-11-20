"""Read license declarations from materialized trees that match the lock."""

from pathlib import Path

import yaml

from .._errors import NSXConfigError
from ..models._module_license import parse_module_licenses
from ..module_registry._metadata import _materialized_module_metadata_path
from ..nsx_lock import _HASH_EXCLUDE_DIRS, NSX_TOOLING_AUTOGEN_FILES, LockKind, NsxLock, hash_tree
from ..project_config import _effective_registry, _load_app_cfg, _load_registry


def locked_module_licenses(app_dir: Path, lock: NsxLock) -> dict[str, dict[str, str | None]]:
    app_dir = app_dir.resolve()
    try:
        config = _load_app_cfg(app_dir)
    except (NSXConfigError, ValueError, OSError):
        config = {}
    registry = _load_registry()
    try:
        registry = _effective_registry(registry, config, app_dir=app_dir)
    except (NSXConfigError, ValueError, OSError):
        # An unavailable workspace overlay must not hide built-in manifests.
        config = {}

    licenses: dict[str, dict[str, str | None]] = {}
    hashes: dict[tuple[Path, frozenset[str]], str] = {}
    for name, entry in lock.modules.items():
        if not entry.vendored_at or not entry.content_hash or entry.kind == LockKind.UNRESOLVED:
            continue
        try:
            root = (app_dir / entry.vendored_at).resolve()
            if root == app_dir or not root.is_relative_to(app_dir) or not root.is_dir():
                continue

            manifest = root / "nsx-module.yaml"
            if entry.kind != LockKind.VENDORED:
                try:
                    manifest = _materialized_module_metadata_path(
                        name, registry, app_dir=app_dir, nsx_cfg=config
                    )
                except (NSXConfigError, ValueError):
                    pass
            if not manifest.is_file() or not manifest.is_relative_to(root):
                continue
            if manifest.resolve() != manifest:
                continue
            if _HASH_EXCLUDE_DIRS.intersection(manifest.relative_to(root).parts):
                continue

            data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or "licenses" not in data
                or data.get("schema_version") != 1
            ):
                continue
            module = data.get("module")
            if not isinstance(module, dict) or module.get("name") != name:
                continue

            excluded = (
                NSX_TOOLING_AUTOGEN_FILES
                if entry.kind == LockKind.PACKAGED and root == app_dir / "cmake" / "nsx"
                else frozenset()
            )
            tree = (root, excluded)
            if tree not in hashes:
                hashes[tree] = hash_tree(root, exclude_names=excluded)
            if hashes[tree] == entry.content_hash:
                try:
                    licenses[name] = parse_module_licenses(data["licenses"], str(manifest))
                except ValueError as exc:
                    raise NSXConfigError(str(exc), field="licenses") from exc
        except (OSError, UnicodeError, yaml.YAMLError):
            # Missing or unreadable vendored sources cannot supply declarations.
            continue

    return licenses
