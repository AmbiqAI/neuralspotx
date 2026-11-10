"""Custom board contracts tested at graph and frozen-build boundaries."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx._errors import NSXLockError, NSXModuleError
from neuralspotx.board_descriptors import BoardDescriptorError, load_board_for_app
from neuralspotx.bsp_contracts import BspBinding
from neuralspotx.metadata import validate_nsx_module_metadata
from neuralspotx.models._module_dependency import parse_required_dependencies
from neuralspotx.module_registry._closure import _resolve_module_closure
from neuralspotx.module_registry._composition import board_composition, verify_board_composition
from neuralspotx.operations._board import create_board_impl


def setup_graph(root: Path, *, local: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    create_board_impl(
        "custom_ap330", from_board="apollo330mP_evb", app_dir=root, bsp_module="custom-bsp"
    )
    registry: dict[str, Any] = {"projects": {}, "modules": {}}
    requirements: dict[str, list[object]] = {
        "consumer": [{"role": "bsp", "contracts": [2]}],
        "custom-bsp": ["hal"],
        "hal": [],
    }
    for name, required in requirements.items():
        data: dict[str, Any] = {
            "schema_version": 1,
            "module": {"name": name, "version": "1.0.0", "type": "runtime"},
            "support": {"ambiqsuite": True, "zephyr": False},
            "build": {"cmake": {"package": name, "targets": [f"nsx::{name}"]}},
            "depends": {"required": required, "optional": []},
            "compatibility": {"boards": ["*"], "socs": ["apollo330P"], "toolchains": ["*"]},
        }
        if name == "custom-bsp":
            data["contracts"] = {"provides": {"bsp": {"versions": [2], "socs": ["apollo330P"]}}}
        directory = root / "modules" / name
        directory.mkdir(parents=True)
        (directory / "nsx-module.yaml").write_text(yaml.safe_dump(data))
        registry["projects"][name] = {
            "local_path": str(directory),
            "path": f"modules/{name}",
            "revision": "local",
        }
        registry["modules"][name] = {
            "project": name,
            "revision": "local",
            "metadata": "nsx-module.yaml",
        }
    cfg: dict[str, Any] = {
        "target": {"board": "custom_ap330", "soc": "apollo330P"},
        "modules": [{"name": "custom-bsp", "local": True}] if local else [],
    }
    return registry, cfg


def resolve(root: Path, registry: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    return _resolve_module_closure(
        ["consumer"],
        app_dir=root,
        registry=registry,
        nsx_cfg=cfg,
        default_toolchain="arm-none-eabi-gcc",
    )


@pytest.mark.parametrize("local", [False, True])
def test_custom_bsp_dependency_is_transparent(tmp_path: Path, local: bool) -> None:
    registry, cfg = setup_graph(tmp_path, local=local)
    assert resolve(tmp_path, registry, cfg) == ["hal", "custom-bsp", "consumer"]
    raw = yaml.safe_load((tmp_path / "boards/custom_ap330/nsx-module.yaml").read_text())
    validate_nsx_module_metadata(raw, "board")


@pytest.mark.parametrize("kind", ["cycle", "version", "soc", "concrete"])
def test_incompatible_graph_fails(tmp_path: Path, kind: str) -> None:
    registry, cfg = setup_graph(tmp_path, local=True)
    path = tmp_path / "modules/custom-bsp/nsx-module.yaml"
    data = yaml.safe_load(path.read_text())
    if kind == "cycle":
        data["depends"]["required"] = ["consumer"]
    elif kind == "version":
        data["contracts"]["provides"]["bsp"]["versions"] = [1]
    elif kind == "soc":
        data["contracts"]["provides"]["bsp"]["socs"] = ["apollo510"]
    else:
        data["depends"]["required"] = ["nsx-ambiq-bsp"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(NSXModuleError):
        resolve(tmp_path, registry, cfg)


@pytest.mark.parametrize(
    "changed",
    [
        "boards/apollo330mP_evb/board.yaml",
        "boards/custom_ap330/board.yaml",
        "modules/custom-bsp/nsx-module.yaml",
        "modules/consumer/nsx-module.yaml",
    ],
)
def test_frozen_contract_inputs_detect_byte_changes(tmp_path: Path, changed: str) -> None:
    registry, cfg = setup_graph(tmp_path)
    names = resolve(tmp_path, registry, cfg)
    record = board_composition(tmp_path, cfg, registry, names)
    verify_board_composition(record, tmp_path, cfg, registry, names)
    path = tmp_path / changed
    path.write_text(path.read_text() + "\n# changed authored input\n")
    with pytest.raises(NSXLockError, match="composition changed"):
        verify_board_composition(record, tmp_path, cfg, registry, names)


@pytest.mark.parametrize("contracts", [[], [True], [0], [2, 2], "2", [2.0]])
def test_strict_requirement_versions(contracts: object) -> None:
    with pytest.raises(ValueError):
        parse_required_dependencies([{"role": "bsp", "contracts": contracts}], "test")


def test_cannot_inherit_binding_or_cycle(tmp_path: Path) -> None:
    setup_graph(tmp_path)
    path = tmp_path / "boards/custom_ap330/board.yaml"
    data = yaml.safe_load(path.read_text())
    data.pop("roles")
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(BoardDescriptorError, match="explicit provider"):
        load_board_for_app("custom_ap330", tmp_path)
    data["roles"] = {"bsp": BspBinding("custom-bsp", 2).to_dict()}
    data["inherits"] = "custom_ap330"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(BoardDescriptorError, match="cycle"):
        load_board_for_app("custom_ap330", tmp_path)


def test_provider_local_dependencies_supply_real_version_metadata(tmp_path: Path) -> None:
    from neuralspotx.module_registry._requirements import validate_materialized_requirements

    registry, cfg = setup_graph(tmp_path, local=True)
    cfg["modules"].append({"name": "hal", "local": True})
    path = tmp_path / "modules/custom-bsp/nsx-module.yaml"
    data = yaml.safe_load(path.read_text())
    data["depends"]["required"] = [{"name": "hal", "version": ">=1.0"}]
    path.write_text(yaml.safe_dump(data))
    names = resolve(tmp_path, registry, cfg)
    assert names == ["hal", "custom-bsp", "consumer"]
    validate_materialized_requirements(names, app_dir=tmp_path, nsx_cfg=cfg, registry=registry)
