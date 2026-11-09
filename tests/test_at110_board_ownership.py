"""NSX-side guards for the deliberately shared AT110 board integration."""

from __future__ import annotations

import yaml

from neuralspotx import board_descriptors as bd
from neuralspotx import load_registry
from neuralspotx.project_config import _effective_registry

BOARD = "atomiq110_fpga_turbo"
MODULE = "nsx-board-atomiq110-fpga-turbo"
METADATA = f"src/neuralspotx/boards/{BOARD}/nsx-module.yaml"


def test_at110_default_registry_owner_is_explicit() -> None:
    registry = load_registry()
    entry = registry["modules"][MODULE]
    assert entry["project"] == "neuralspotx"
    assert entry["metadata"] == METADATA
    # An SDK project can coexist without becoming another implicit board owner.
    assert "nsx-ambiq-sdk" in registry["projects"]


def test_at110_explicit_app_override_preserves_precedence() -> None:
    registry = load_registry()
    override = {
        "project": "custom-board-provider",
        "revision": "v1.0.0",
        "metadata": "boards/custom/nsx-module.yaml",
    }
    result = _effective_registry(
        registry,
        {"module_registry": {"modules": {MODULE: override}}},
    )
    assert result["modules"][MODULE] == override
    assert registry["modules"][MODULE]["project"] == "neuralspotx"


def test_at110_manifest_matches_descriptor_and_public_board_contract() -> None:
    descriptor = bd.load_board(BOARD)
    assert descriptor is not None
    manifest = yaml.safe_load((descriptor.path / "nsx-module.yaml").read_text(encoding="utf-8"))
    assert manifest["module"]["name"] == MODULE
    assert manifest["module"]["type"] == "board"
    assert manifest["compatibility"]["boards"] == [descriptor.name]
    assert manifest["compatibility"]["socs"] == [descriptor.soc]
    assert set(manifest["compatibility"]["toolchains"]) == set(descriptor.toolchains)
    assert descriptor.sdk_provider == "ambiqsuite"
    assert manifest["constraints"]["required_sdk_provider"] == "nsx-ambiqsuite"
    assert manifest["build"]["cmake"] == {
        "package": "nsx_board_atomiq110_fpga_turbo",
        "targets": ["nsx::board_atomiq110_fpga_turbo"],
    }
    assert set(manifest["depends"]["required"]) == {
        "nsx-ambiq-hal",
        "nsx-ambiq-bsp",
        "nsx-soc-hal",
        "nsx-cmsis-startup",
        "nsx-ambiqsuite",
    }
