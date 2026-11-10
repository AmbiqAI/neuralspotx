"""Compute the board contract fingerprint without fetching dependencies."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from .._errors import NSXLockError, NSXResolutionError
from ..board_plan import resolve_board_plan
from ..bsp_contracts import BspRequirement
from ..nsx_lock._composition import BoardComposition, CompositionInput
from ._bsp import load_bsp_local_dependencies, participant_metadata_path, read_participant
from ._metadata import _load_materialized_module_metadata, _load_module_metadata
from ._nsx_cfg import _local_module_names, _vendored_module_names


def _input_hash(path: Path) -> str:
    """Hash authored YAML bytes, normalizing CRLF checkouts to LF only."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def board_composition(
    app_dir: Path,
    config: dict[str, Any],
    registry: dict[str, Any],
    modules: list[str],
    *,
    materialized: bool = False,
    read_only_record: BoardComposition | None = None,
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
    recorded_participants = (
        {entry.name: entry for entry in read_only_record.contract_inputs}
        if read_only_record
        else {}
    )
    for name in sorted(modules):
        if name in opaque and name != descriptor.bsp.module and name not in recorded_participants:
            continue
        try:
            path = participant_metadata_path(
                name, registry, app_dir, config, materialized=materialized
            )
            if not path.is_file():
                raise NSXResolutionError(f"Missing BSP composition input: {path}")
        except NSXResolutionError:
            # The caller has already warned that a read-only locked-closure
            # fallback cannot certify unavailable metadata. Retain only those
            # unavailable inputs; every available input is parsed and rehashed.
            if read_only_record is not None and not materialized:
                if name in recorded_participants:
                    contract_inputs.append(recorded_participants[name])
                continue
            raise
        if name in opaque:
            meta = read_participant(name, path)
        elif materialized:
            meta = _load_materialized_module_metadata(
                name, registry, app_dir=app_dir, nsx_cfg=config
            )
        else:
            meta = _load_module_metadata(name, registry, app_dir=app_dir)
        metadata[name] = meta
    if read_only_record is None or materialized:
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
            contract_inputs.append(CompositionInput(name, _input_hash(path)))
    inputs = tuple(
        sorted(
            (CompositionInput(p.parent.name, _input_hash(p)) for p in descriptor.descriptor_inputs),
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
        tuple(sorted(contract_inputs, key=lambda entry: entry.name)),
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
