"""Module-graph correctness policies enforced during closure resolution."""

from __future__ import annotations

from typing import Any

from .._errors import NSXModuleError


def _validate_board_module_dep_policy(
    module_name: str,
    metadata: dict[str, Any],
    resolver: dict[str, dict[str, Any]],
) -> None:
    if metadata["module"]["type"] != "board":
        return
    required = metadata["depends"]["required"]
    soc_count = 0
    for dep_name in required:
        dep_meta = resolver.get(dep_name)
        if dep_meta is None:
            continue
        if dep_meta["module"]["type"] == "soc":
            soc_count += 1
    if soc_count != 1:
        raise NSXModuleError(
            f"Board module '{module_name}' must depend on exactly one soc module. "
            f"Found soc dependency count={soc_count}"
        )


def _validate_sdk_provider_policy(
    module_name: str,
    metadata: dict[str, Any],
    resolver: dict[str, dict[str, Any]],
) -> None:
    constraints = metadata.get("constraints", {})
    if not isinstance(constraints, dict):
        return
    required_provider = constraints.get("required_sdk_provider")
    if not isinstance(required_provider, str):
        return

    provider_names = [
        name
        for name, meta in resolver.items()
        if meta.get("module", {}).get("type") == "sdk_provider"
    ]
    if required_provider not in provider_names:
        raise NSXModuleError(
            f"Module '{module_name}' requires SDK provider '{required_provider}' "
            "but it is not enabled in the resolved dependency closure."
        )
