"""Author-facing YAML type checks and custom-board round trips."""

from pathlib import Path

import pytest
import yaml

from neuralspotx import create_board
from neuralspotx.board_descriptors import BOARDS_DIR, BoardDescriptorError, load_board_for_app
from neuralspotx.metadata import load_registry_lock, load_yaml, validate_nsx_module_metadata


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("board.registered", "false"),
        ("board.registered", 1),
        ("board.registered", None),
        ("board.soc", None),
        ("board.tier", []),
        ("sdk_provider", False),
        ("cpu.core", 55),
        ("cpu.float_abi", {}),
        ("cpu.abi", "  "),
        ("inherits", True),
        ("toolchains", False),
    ],
)
def test_board_reports_bad_field_and_source(tmp_path: Path, field: str, value: object):
    path = tmp_path / "boards" / "apollo510_evb" / "board.yaml"
    path.parent.mkdir(parents=True)
    raw = load_yaml(BOARDS_DIR / "apollo510_evb" / "board.yaml")
    group, _, key = field.rpartition(".")
    (raw[group] if group else raw)[key] = value
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(BoardDescriptorError) as error:
        load_board_for_app("apollo510_evb", tmp_path)
    assert str(path) in str(error.value)
    assert field in str(error.value)


@pytest.mark.parametrize(("field", "invalid"), [("cpu", None), ("cpu", {}), ("overrides", False)])
def test_inherited_defaults_only_when_omitted(tmp_path: Path, field: str, invalid: object):
    board = create_board("child", from_board="apollo510_evb", app_dir=tmp_path)
    assert board.cpu.core == "cortex-m55"
    path = board.path / "board.yaml"
    raw = load_yaml(path)
    raw[field] = invalid
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(BoardDescriptorError) as error:
        load_board_for_app("child", tmp_path)
    assert str(path) in str(error.value) and field in str(error.value)


@pytest.mark.parametrize("version", [True, "1", 1.0, None, 2])
@pytest.mark.parametrize("filename", ["registry.lock.yaml", "nsx-module.yaml"])
def test_metadata_versions_require_the_declared_integer(tmp_path: Path, filename: str, version):
    path = tmp_path / filename
    if filename == "registry.lock.yaml":
        data = {
            "schema_version": 1,
            "channels": {},
            "projects": {},
            "modules": {},
            "starter_profiles": {},
        }
    else:
        data = load_yaml(BOARDS_DIR / "apollo510_evb" / filename)
    data["schema_version"] = version
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError) as error:
        if filename == "registry.lock.yaml":
            load_registry_lock(path)
        else:
            validate_nsx_module_metadata(load_yaml(path), str(path))
    assert str(path) in str(error.value) and "schema_version" in str(error.value)


def test_generated_yaml_preserves_string_identifiers(tmp_path: Path):
    parent = create_board("No", from_board="apollo330mP_evb", app_dir=tmp_path)
    child = create_board("On", from_board=parent.name, bsp_module="Off", app_dir=tmp_path)
    assert (child.name, child.bsp.module, child.soc) == ("On", "Off", "apollo330P")
    path = child.path / "nsx-module.yaml"
    module = load_yaml(path)
    validate_nsx_module_metadata(module, str(path))
    assert module["compatibility"]["boards"] == ["On"]
