"""Packaged board modules must accept the toolchains their descriptors advertise.

``nsx lock`` gates every module in the closure through ``is_compatible``
against the target's ``toolchain``. For a packaged board that gate reads the
``compatibility.toolchains`` list in ``boards/<board>/nsx-module.yaml``, so a
board whose descriptor (``board.yaml``) advertises a toolchain its module does
not declare fails at lock time before anything is built — which is how the
apollo4l boards refused ATfE (AmbiqAI/helia-profiler#310). These tests pin the
two files to each other and resolve the real packaged metadata, not synthetic
fixtures, through the same gate.
"""

from __future__ import annotations

import pytest

from neuralspotx import board_descriptors as bd
from neuralspotx.metadata import is_compatible, load_yaml, registry_entry_for_module
from neuralspotx.module_registry import packaged_module_metadata_path
from neuralspotx.project_config import _load_registry


def _packaged_board_module(board: str) -> tuple[str, dict]:
    """Return ``(module_name, metadata)`` for the packaged module of *board*."""
    registry = _load_registry()
    expected = f"src/neuralspotx/boards/{board}/nsx-module.yaml"
    names = [
        name
        for name, entry in registry["modules"].items()
        if entry.get("project") == "neuralspotx" and entry.get("metadata") == expected
    ]
    assert len(names) == 1, f"{board}: expected one packaged board module, got {names}"
    entry = registry_entry_for_module(registry, names[0])
    return names[0], load_yaml(packaged_module_metadata_path(names[0], entry, registry))


@pytest.mark.parametrize("board", ["apollo4l_evb", "apollo4l_blue_evb"])
def test_apollo4l_boards_accept_atfe(board: str) -> None:
    desc = bd.load_board(board)
    assert desc is not None
    assert "atfe" in desc.toolchains
    module_name, metadata = _packaged_board_module(board)
    assert is_compatible(metadata, board=board, soc=desc.soc, toolchain="atfe"), (
        f"{module_name} refuses toolchain=atfe for {board}"
    )


@pytest.mark.parametrize(
    "board",
    sorted(name for name, desc in bd.load_board_descriptors().items() if desc.registered),
)
def test_registered_board_module_accepts_every_advertised_toolchain(board: str) -> None:
    """A descriptor must never advertise a toolchain the packaged module refuses."""

    desc = bd.load_board(board)
    assert desc is not None
    module_name, metadata = _packaged_board_module(board)
    declared = set(metadata["compatibility"]["toolchains"])
    for toolchain in desc.toolchains:
        assert is_compatible(metadata, board=board, soc=desc.soc, toolchain=toolchain), (
            f"{board}: board.yaml advertises {toolchain} but {module_name} declares {declared}"
        )
