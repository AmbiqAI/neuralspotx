"""Shared request DTOs consumed by both the public API and the operations layer.

These live in :mod:`neuralspotx.models` (the neutral leaf layer) rather than in
:mod:`neuralspotx.api` so that ``operations`` impls can accept them directly
without importing the higher ``api`` layer (which would invert the dependency
direction) and without re-declaring the field list (which would be a drift
hazard). The public ``neuralspotx.api`` surface re-exports these names, so the
historic import paths continue to work unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PathLike = str | Path


@dataclass(slots=True)
class ModuleInitRequest:
    """Describe a custom-module skeleton to create.

    Attributes:
        module_dir: Destination directory for the generated module.
        module_name: Manifest module name. Defaults to the destination directory name.
        module_type: NSX module type written to ``nsx-module.yaml``.
        summary: Human-readable module summary. A placeholder is generated when omitted.
        version: Initial semantic version written to the module metadata.
        dependencies: Required NSX module names, in declaration order.
        boards: Compatible board names. Defaults to all boards.
        socs: Compatible SoC names. Defaults to all SoCs.
        toolchains: Compatible toolchain names. Defaults to the NSX default toolchain.
        force: Allow generation into an existing non-empty directory.
    """

    module_dir: PathLike
    module_name: str | None = None
    module_type: str = "runtime"
    summary: str | None = None
    version: str = "0.1.0"
    dependencies: list[str] | None = None
    boards: list[str] | None = None
    socs: list[str] | None = None
    toolchains: list[str] | None = None
    force: bool = False
