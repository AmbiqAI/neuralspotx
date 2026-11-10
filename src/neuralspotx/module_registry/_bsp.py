"""Bind explicit BSP role dependencies; validate participating local manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .._errors import NSXModuleError
from ..board_plan import ResolvedBoardPlan
from ..bsp_contracts import BspRequirement
from ..metadata import registry_entry_for_module, validate_nsx_module_metadata
from ..models import ModuleDependency, ModuleMetadata
from ..project_config import _registry_project_entry
from ._metadata import _materialized_module_metadata_path, _module_metadata_path


def participant_metadata_path(
    name: str,
    registry: dict[str, Any],
    app_dir: Path,
    config: dict[str, Any],
    *,
    materialized: bool = False,
) -> Path:
    """The actual compiled snapshot for checks; explicit source for writable resolution."""
    try:
        entry = registry_entry_for_module(registry, name)
    except ValueError:
        return app_dir / "modules" / name / "nsx-module.yaml"
    if materialized:
        return _materialized_module_metadata_path(name, registry, app_dir=app_dir, nsx_cfg=config)
    project = _registry_project_entry(registry, entry.project)
    # Source:path normalization may contain an absolute metadata path. A BSP
    # local module always authors its contract at the selected module root.
    if project.local_path and name in {
        m.get("name") for m in config.get("modules", []) if m.get("local")
    }:
        return Path(project.local_path) / "nsx-module.yaml"
    return _module_metadata_path(name, entry, registry, app_dir=app_dir)


def read_participant(name: str, path: Path) -> ModuleMetadata:
    if not path.is_file():
        raise NSXModuleError(
            f"BSP participant '{name}' requires metadata at {path}; add nsx-module.yaml"
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise NSXModuleError(f"{path}: expected a module metadata mapping")
    validate_nsx_module_metadata(raw, str(path))
    meta = ModuleMetadata.from_raw(raw)
    if meta.name != name:
        raise NSXModuleError(f"{path}: module.name must be '{name}', got '{meta.name}'")
    return meta


def validate_bsp_offer(plan: ResolvedBoardPlan, metadata: ModuleMetadata) -> None:
    binding = plan.descriptor.bsp
    if metadata.name != binding.module:
        raise NSXModuleError(f"Selected BSP '{binding.module}' has metadata for '{metadata.name}'")
    offer = metadata.bsp_offer
    if binding.contract == 1 and binding.module == "nsx-ambiq-bsp":
        return
    if (
        offer is None
        or binding.contract not in offer.versions
        or plan.descriptor.soc not in offer.socs
    ):
        raise NSXModuleError(
            f"BSP '{binding.module}' must offer contract {binding.contract} for {plan.descriptor.soc}; "
            "select compatible provider metadata, then run `nsx lock`"
        )


def bind_requirements(
    metadata: ModuleMetadata, plan: ResolvedBoardPlan | None
) -> list[ModuleDependency]:
    bound: list[ModuleDependency] = []
    for dep in metadata.required_dependencies:
        if isinstance(dep, BspRequirement):
            if plan is None:
                raise NSXModuleError(
                    f"Module '{metadata.name}' requires a BSP role but no board binding exists"
                )
            binding = plan.descriptor.bsp
            if binding.contract not in dep.contracts:
                raise NSXModuleError(
                    f"Module '{metadata.name}' requires BSP contracts {dep.contracts}, "
                    f"board selects {binding.contract}"
                )
            bound.append(ModuleDependency(binding.module))
        else:
            if plan and dep.name == "nsx-ambiq-bsp" and plan.descriptor.bsp.module != dep.name:
                raise NSXModuleError(
                    f"Module '{metadata.name}' requires concrete EVB BSP '{dep.name}', "
                    "which conflicts with the selected custom BSP; adapt its declared dependency"
                )
            bound.append(dep)
    return bound
