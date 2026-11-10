"""Compute the board contract fingerprint without fetching dependencies."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from .._errors import NSXLockError
from ..board_plan import resolve_board_plan
from ..bsp_contracts import BspRequirement
from ..nsx_lock._composition import BoardComposition, CompositionInput
from ._bsp import load_bsp_local_dependencies, participant_metadata_path, read_participant
from ._metadata import _load_materialized_module_metadata, _load_module_metadata
from ._nsx_cfg import _local_module_names, _vendored_module_names


def board_composition(
    app_dir: Path,
    config: dict[str, Any],
    registry: dict[str, Any],
    modules: list[str],
    *,
    materialized: bool = False,
) -> BoardComposition | None:
    plan = resolve_board_plan(app_dir, config)
    if plan is None or not modules:
        return None
    descriptor = plan.descriptor
    if descriptor.bsp.module not in modules:
        return None
    opaque = _local_module_names(config) | _vendored_module_names(config)
    contract_inputs = []
    metadata = {}
    for name in sorted(modules):
        if name in opaque and name != descriptor.bsp.module:
            continue
        path = participant_metadata_path(name, registry, app_dir, config, materialized=materialized)
        if name == descriptor.bsp.module and name in opaque:
            meta = read_participant(name, path)
        elif materialized:
            meta = _load_materialized_module_metadata(
                name, registry, app_dir=app_dir, nsx_cfg=config
            )
        else:
            meta = _load_module_metadata(name, registry, app_dir=app_dir)
        metadata[name] = meta
    load_bsp_local_dependencies(
        metadata, plan, opaque, registry, app_dir, config, materialized=materialized
    )
    for name, meta in sorted(metadata.items()):
        path = participant_metadata_path(name, registry, app_dir, config, materialized=materialized)
        if (
            name == descriptor.bsp.module
            or meta.bsp_offer is not None
            or any(isinstance(dep, BspRequirement) for dep in meta.required_dependencies)
        ):
            contract_inputs.append(CompositionInput(name, sha256(path.read_bytes()).hexdigest()))
    inputs = tuple(
        sorted(
            (
                CompositionInput(p.parent.name, sha256(p.read_bytes()).hexdigest())
                for p in descriptor.descriptor_inputs
            ),
            key=lambda r: r.name,
        )
    )
    return BoardComposition(
        descriptor.name,
        descriptor.revision,
        descriptor.soc,
        descriptor.sdk_provider,
        descriptor.bsp,
        inputs,
        tuple(contract_inputs),
    )


def verify_board_composition(
    expected: BoardComposition | None,
    app_dir: Path,
    config: dict[str, Any],
    registry: dict[str, Any],
    modules: list[str],
) -> None:
    current = board_composition(app_dir, config, registry, modules, materialized=True)
    if current != expected:
        raise NSXLockError(
            "Board/BSP composition changed since nsx.lock; run `nsx lock` and `nsx sync` before building"
        )
