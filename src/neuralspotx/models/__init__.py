"""Typed internal models for NSX registry, manifest, and app metadata.

This module is a thin facade: every name below is re-exported from a
sibling submodule under :mod:`neuralspotx.models`. Importers using the
historic ``from neuralspotx.models import X`` path continue to work
unchanged. New code may import from the leaf submodules directly.
"""

from __future__ import annotations

from ._cache import CacheCleanResult, CacheEntry, CacheInfo
from ._changes import ModuleChange
from ._command import (
    CommandCategory,
    CommandHint,
    CommandScope,
    DoctorCheck,
    DoctorReport,
)
from ._discovery import DiscoveryRecord, SearchMatch, SearchResult
from ._loader import NsxProject
from ._outdated import OutdatedModule, OutdatedReport, OutdatedSkip
from ._project import (
    AppConfig,
    AppModule,
    ModuleEntry,
    ModuleRegistryOverride,
    ModuleSource,
    ProjectEntry,
    ResolvedTarget,
)
from ._requests import ModuleInitRequest

__all__ = [
    "AppConfig",
    "AppModule",
    "ResolvedTarget",
    "CacheCleanResult",
    "CacheEntry",
    "CacheInfo",
    "CommandCategory",
    "CommandHint",
    "CommandScope",
    "DiscoveryRecord",
    "DoctorCheck",
    "DoctorReport",
    "ModuleChange",
    "ModuleEntry",
    "ModuleInitRequest",
    "ModuleRegistryOverride",
    "ModuleSource",
    "NsxProject",
    "OutdatedModule",
    "OutdatedReport",
    "OutdatedSkip",
    "ProjectEntry",
    "SearchMatch",
    "SearchResult",
]
