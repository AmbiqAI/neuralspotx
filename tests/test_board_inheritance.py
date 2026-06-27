"""Phase 3: custom-board inheritance + scaffolding (``inherits`` / ``overrides``).

Covers :func:`board_descriptors.load_board_descriptor_file` resolving an
``inherits`` link, the ``overrides.toolchains`` delta syntax, full-list
replacement, error cases, and the ``render_custom_board_*`` helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neuralspotx import board_descriptors as bd
from neuralspotx.board_descriptors import BoardDescriptorError


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_inherits_pulls_parent_facts(tmp_path: Path) -> None:
    parent = bd.load_board("apollo510_evb")
    assert parent is not None
    board_yaml = _write(
        tmp_path / "boards" / "my_apollo510" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo510_evb\n"
        "board:\n"
        "  name: my_apollo510\n"
        "  tier: custom\n"
        "  registered: false\n",
    )
    desc = bd.load_board_descriptor_file(board_yaml)
    assert desc.name == "my_apollo510"
    assert desc.tier == "custom"
    assert desc.registered is False
    # Inherited scalar facts.
    assert desc.soc == parent.soc
    assert desc.sdk_provider == parent.sdk_provider
    assert desc.cpu == parent.cpu
    assert desc.toolchains == parent.toolchains


def test_overrides_toolchains_delta_removes(tmp_path: Path) -> None:
    parent = bd.load_board("apollo510_evb")
    assert parent is not None
    assert "armclang" in parent.toolchains
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo510_evb\n"
        "board:\n"
        "  name: custom\n"
        "overrides:\n"
        "  toolchains: [-armclang]\n",
    )
    desc = bd.load_board_descriptor_file(board_yaml)
    assert "armclang" not in desc.toolchains
    # Everything else from the parent is preserved, order intact.
    expected = tuple(t for t in parent.toolchains if t != "armclang")
    assert desc.toolchains == expected


def test_overrides_toolchains_delta_adds(tmp_path: Path) -> None:
    parent = bd.load_board("apollo3_evb")
    assert parent is not None
    assert "armclang" not in parent.toolchains
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo3_evb\n"
        "board:\n"
        "  name: custom\n"
        "overrides:\n"
        "  toolchains: [+armclang]\n",
    )
    desc = bd.load_board_descriptor_file(board_yaml)
    assert "armclang" in desc.toolchains
    assert set(parent.toolchains).issubset(set(desc.toolchains))


def test_overrides_toolchains_full_replacement(tmp_path: Path) -> None:
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo510_evb\n"
        "board:\n"
        "  name: custom\n"
        "overrides:\n"
        "  toolchains: [gcc]\n",
    )
    desc = bd.load_board_descriptor_file(board_yaml)
    assert desc.toolchains == ("gcc",)


def test_overrides_mixing_plain_and_prefixed_raises(tmp_path: Path) -> None:
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo510_evb\n"
        "board:\n"
        "  name: custom\n"
        "overrides:\n"
        "  toolchains: [gcc, -armclang]\n",
    )
    with pytest.raises(BoardDescriptorError, match="mix plain and"):
        bd.load_board_descriptor_file(board_yaml)


def test_inherits_unknown_board_raises(tmp_path: Path) -> None:
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: not_a_real_board\n"
        "board:\n"
        "  name: custom\n",
    )
    with pytest.raises(BoardDescriptorError, match="inherits unknown board"):
        bd.load_board_descriptor_file(board_yaml)


def test_inherits_with_explicit_parent_lookup(tmp_path: Path) -> None:
    parent = bd.load_board("apollo510_evb")
    assert parent is not None
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: my_base\n"
        "board:\n"
        "  name: custom\n",
    )
    desc = bd.load_board_descriptor_file(
        board_yaml, parent_lookup={"my_base": parent}
    )
    assert desc.soc == parent.soc
    assert desc.sdk_provider == parent.sdk_provider


def test_child_scalar_overrides_parent(tmp_path: Path) -> None:
    board_yaml = _write(
        tmp_path / "boards" / "custom" / "board.yaml",
        "schema_version: 1\n"
        "inherits: apollo510_evb\n"
        "board:\n"
        "  name: custom\n"
        "  soc: apollo510_custom\n",
    )
    desc = bd.load_board_descriptor_file(board_yaml)
    assert desc.soc == "apollo510_custom"


def test_render_custom_board_yaml_roundtrips(tmp_path: Path) -> None:
    text = bd.render_custom_board_yaml(name="my_board", parent="apollo510_evb")
    board_yaml = _write(tmp_path / "boards" / "my_board" / "board.yaml", text)
    desc = bd.load_board_descriptor_file(board_yaml)
    parent = bd.load_board("apollo510_evb")
    assert parent is not None
    assert desc.name == "my_board"
    assert desc.tier == "custom"
    assert desc.registered is False
    assert desc.soc == parent.soc
    assert desc.toolchains == parent.toolchains


def test_render_custom_board_cmake_delegates_to_parent() -> None:
    text = bd.render_custom_board_cmake(name="my_board", parent="apollo510_evb")
    assert "apollo510_evb" in text
    assert "nsx::board_my_board" in text
    assert "${NSX_ROOT}/boards/${NSX_PARENT_BOARD}/board.cmake" in text
