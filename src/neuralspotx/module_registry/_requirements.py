"""Required-version checks shared by graph resolution and materialized builds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .._errors import NSXConfigError, NSXModuleError
from ..models import ModuleDependency, ModuleMetadata
from ._metadata import _load_module_metadata, metadata_cache_scope
from ._nsx_cfg import _local_module_names, _vendored_module_names


def validate_requirement(
    parent: str, dependency: ModuleDependency, metadata: ModuleMetadata | None
) -> None:
    """Check one edge, regardless of whether another parent already visited it."""
    if dependency.version is None:
        return
    prefix = f"Module '{parent}' requires '{dependency.name}' version {dependency.version!r}"
    if metadata is None:
        raise NSXModuleError(
            f"{prefix}, but its source is opaque. Provide registry-backed module metadata "
            "to validate its version."
        )
    observed = metadata.version
    try:
        version = Version(observed)
    except InvalidVersion as exc:
        raise NSXModuleError(
            f"{prefix}, but module.version is {observed!r}, not a PEP 440 version. "
            "Correct the dependency metadata or select a compatible registry revision."
        ) from exc
    specifier = SpecifierSet(dependency.version)
    if not specifier.contains(version, prereleases=bool(specifier.prereleases)):
        raise NSXModuleError(
            f"{prefix}, but module.version is {observed!r}. Select a compatible registry "
            "revision, then run `nsx lock` and `nsx sync`."
        )


def requirement_metadata_error(
    parent: str, dep: ModuleDependency, exc: Exception
) -> NSXModuleError:
    return NSXModuleError(
        f"Module '{parent}' requires '{dep.name}' version {dep.version!r}, "
        f"but its metadata is invalid: {exc}. Correct nsx-module.yaml or select a "
        "compatible registry revision, then run `nsx lock` and `nsx sync`."
    )


def validate_materialized_requirements(
    module_names: list[str], *, app_dir: Path, nsx_cfg: dict[str, Any], registry: dict[str, Any]
) -> None:
    """Validate locked members without fetching or expanding the recorded graph."""
    opaque = _local_module_names(nsx_cfg) | _vendored_module_names(nsx_cfg)
    metadata: dict[str, ModuleMetadata] = {}
    errors: dict[str, ValueError | NSXConfigError] = {}
    positions = {name: index for index, name in enumerate(module_names)}
    with metadata_cache_scope(fresh=True):
        for name in module_names:
            if name in opaque:
                continue
            try:
                metadata[name] = _load_module_metadata(name, registry, app_dir=app_dir)
            except (ValueError, NSXConfigError) as exc:
                errors[name] = exc
        for name, meta in metadata.items():
            for dep in meta.required_dependencies:
                if dep.name not in positions:
                    raise NSXModuleError(
                        f"Module '{name}' requires '{dep.name}', which is absent from nsx.lock. "
                        "Run `nsx lock` and `nsx sync` to refresh the dependency closure."
                    )
                if dep.version is not None and dep.name in errors:
                    raise requirement_metadata_error(name, dep, errors[dep.name])
                validate_requirement(name, dep, metadata.get(dep.name))
                if positions[dep.name] >= positions[name]:
                    raise NSXModuleError(
                        f"Module '{name}' requires '{dep.name}', but nsx.lock does not "
                        "place that dependency first (stale order or dependency cycle). "
                        "Run `nsx lock` and `nsx sync` after correcting any cycle."
                    )
        if errors:
            name, exc = next(iter(errors.items()))
            raise NSXModuleError(f"Invalid metadata for module '{name}': {exc}") from exc
