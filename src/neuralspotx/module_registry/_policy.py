"""Module-graph correctness policies enforced during closure resolution."""

from __future__ import annotations

from .._errors import NSXModuleError
from ..models import ModuleMetadata


def _validate_board_module_dep_policy(
    module_name: str,
    metadata: ModuleMetadata,
    resolver: dict[str, ModuleMetadata],
) -> None:
    if metadata.module_type != "board":
        return
    required = metadata.required_deps
    soc_count = 0
    for dep_name in required:
        dep_meta = resolver.get(dep_name)
        if dep_meta is None:
            continue
        if dep_meta.module_type == "soc":
            soc_count += 1
    if soc_count != 1:
        raise NSXModuleError(
            f"Board module '{module_name}' must depend on exactly one soc module. "
            f"Found soc dependency count={soc_count}"
        )


def _validate_sdk_provider_policy(
    module_name: str,
    metadata: ModuleMetadata,
    resolver: dict[str, ModuleMetadata],
) -> None:
    required_provider = metadata.required_sdk_provider
    if required_provider is None:
        return

    provider_names = [
        name
        for name, meta in resolver.items()
        if meta.module_type == "sdk_provider"
    ]
    if required_provider not in provider_names:
        raise NSXModuleError(
            f"Module '{module_name}' requires SDK provider '{required_provider}' "
            "but it is not enabled in the resolved dependency closure."
        )
