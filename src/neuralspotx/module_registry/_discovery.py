"""``DiscoveryRecord`` builders backing ``nsx module list/search/describe``."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .._errors import NSXError
from ..metadata import registry_entry_for_module
from ..models import DiscoveryRecord
from ._metadata import _load_module_metadata, metadata_cache_scope


def _module_discovery_record(
    module_name: str,
    registry: dict[str, Any],
    *,
    app_dir: Path | None = None,
    enabled: bool = False,
    include_metadata: bool = True,
) -> DiscoveryRecord:
    entry = registry_entry_for_module(registry, module_name)
    core = dict(
        name=module_name,
        project=entry.project,
        revision=entry.revision,
        metadata=entry.metadata,
        enabled=enabled,
    )
    if not include_metadata:
        return DiscoveryRecord(**core)

    try:
        metadata = _load_module_metadata(module_name, registry, app_dir=app_dir)
    except NSXError as exc:
        error_msg = (
            f"{exc} Provide --app-dir to resolve external module metadata."
            if app_dir is None
            else str(exc)
        )
        return DiscoveryRecord(**core, metadata_error=error_msg)

    kwargs: dict[str, Any] = {}
    for key in (
        "summary",
        "capabilities",
        "use_cases",
        "anti_use_cases",
        "agent_keywords",
        "example_refs",
        "composition_hints",
    ):
        if key in metadata:
            kwargs[key] = copy.deepcopy(metadata[key])
    for key in ("provides", "constraints", "integrations"):
        if key in metadata:
            kwargs[key] = copy.deepcopy(metadata[key])

    return DiscoveryRecord(
        **core,
        metadata_available=True,
        module=copy.deepcopy(metadata["module"]),
        support=copy.deepcopy(metadata["support"]),
        build=copy.deepcopy(metadata["build"]),
        depends=copy.deepcopy(metadata["depends"]),
        compatibility=copy.deepcopy(metadata["compatibility"]),
        **kwargs,
    )


def _module_discovery_records(
    registry: dict[str, Any],
    enabled: set[str],
    *,
    app_dir: Path | None = None,
    include_metadata: bool = True,
) -> list[DiscoveryRecord]:
    with metadata_cache_scope():
        return [
            _module_discovery_record(
                name,
                registry,
                app_dir=app_dir,
                enabled=name in enabled,
                include_metadata=include_metadata,
            )
            for name in sorted(registry["modules"].keys())
        ]
