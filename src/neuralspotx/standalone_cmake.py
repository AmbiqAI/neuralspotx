"""Publish portable CMake snapshots only after dependency preparation succeeds."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


from .constants import normalize_board
from .models import AppConfig, ModuleMetadata


def snapshot_path(app_dir: Path, board: str) -> Path:
    return app_dir / "cmake" / "nsx-resolved" / normalize_board(board) / "modules.cmake"


def invalidate_snapshot(app_dir: Path, board: str) -> None:
    """A changed lock cannot certify a previously prepared source snapshot."""
    from .project_config import _write_module_input

    path = snapshot_path(app_dir, board)
    if path.exists():
        _write_module_input(
            path, 'message(FATAL_ERROR "NSX inputs need preparation; run nsx sync.")\n'
        )


def _quote(value: str) -> str:
    # Generated CMake must preserve filenames literally, including $ and ;.
    return (
        '"'
        + value.replace("\\", "/").replace('"', '\\"').replace("$", "\\$").replace(";", "\\;")
        + '"'
    )


def publish_snapshot(app_dir: Path, config: dict[str, Any], modules: list[str]) -> None:
    """Freeze a prepared closure; never call this from ordinary build refreshes.

    The caller owns resolution/materialization validation. This is a declaration
    drift check, not a replacement for frozen sync's complete content hashes.
    """
    from .board_plan import resolve_board_plan
    from .module_registry._bsp import load_bsp_local_dependencies, participant_metadata_path
    from .module_registry._closure import _compat_check_skipped
    from .module_registry._metadata import _read_module_metadata
    from .project_config import (
        _effective_registry,
        _load_registry,
        _module_source_dir_relative_to_app,
        _write_module_input,
    )

    app = AppConfig.from_mapping(config)
    board = normalize_board(str(app.target.get("board") or app.default_board()))
    registry = _effective_registry(_load_registry(), config, app_dir=app_dir)

    compiler_ids = {"GNU", "ARMClang", "ArmClang", "Clang"}
    constraints: dict[str, ModuleMetadata] = {}
    opaque = app.local_module_names() | app.vendored_module_names()
    metadata = {Path("nsx.yml")}
    required = set()
    plan = resolve_board_plan(app_dir, config)
    if plan and plan.descriptor.bsp.module in modules:
        for path in plan.descriptor.descriptor_inputs:
            # Board descriptors selected from packaged defaults must also be
            # copied locally by preparation before claiming portability.
            local = Path("boards") / path.parent.name / path.name
            metadata.add(local)
            required.add(local)
    for name in modules:
        directory = _module_source_dir_relative_to_app(name, registry, config)
        if directory.parts[:1] == ("modules",):
            required.add(directory / "CMakeLists.txt")
        path = participant_metadata_path(name, registry, app_dir, config, materialized=True)
        if path.is_relative_to(app_dir):
            metadata.add(path.relative_to(app_dir))
        if path.is_file() and name not in opaque:
            constraints[name] = _read_module_metadata(path, name)

    if plan and plan.descriptor.bsp.module in modules:
        # Match closure resolution: BSP-reachable local dependencies participate
        # in compatibility checks even though unrelated local modules are opaque.
        load_bsp_local_dependencies(
            constraints, plan, opaque, registry, app_dir, config, materialized=True
        )
    if not _compat_check_skipped():
        for module in constraints.values():
            supported = module.compatibility["toolchains"]
            if "*" in supported:
                continue
            accepted = set()
            if "gcc" in supported or "arm-none-eabi-gcc" in supported:
                accepted.add("GNU")
            if "armclang" in supported:
                accepted.update({"ARMClang", "ArmClang"})
            if "atfe" in supported:
                accepted.add("Clang")
            compiler_ids.intersection_update(accepted)

    lines = ["# Prepared NSX closure. Regenerate with nsx sync; do not edit."]
    lines.append("_nsx_check_compiler(" + " ".join(sorted(compiler_ids)) + ")")
    for path in sorted(metadata):
        absolute = app_dir / path
        digest = (
            hashlib.sha256(absolute.read_bytes()).hexdigest() if absolute.is_file() else "absent"
        )
        lines.append(f"_nsx_check_metadata({_quote(path.as_posix())} {_quote(digest)})")
    for path in sorted(required):
        lines.append(f"_nsx_require_file({_quote(path.as_posix())})")
    content = (app_dir / "build" / board / "nsx" / "modules.cmake").read_text(encoding="utf-8")
    _write_module_input(app_dir / "cmake" / "nsx-resolved" / ".gitignore", "*\n")
    _write_module_input(snapshot_path(app_dir, board), "\n".join(lines) + "\n" + content)
