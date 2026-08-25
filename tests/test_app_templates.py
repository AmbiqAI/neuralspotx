"""No-network tests for ``create-app`` template selection."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from neuralspotx._errors import NSXConfigError
from neuralspotx.operations import APP_TEMPLATES, create_app_impl


def test_app_templates_registry_shape() -> None:
    assert "default" in APP_TEMPLATES
    assert "npu-tflm" in APP_TEMPLATES
    assert APP_TEMPLATES["default"].modules == ()
    assert APP_TEMPLATES["npu-tflm"].modules == ("nsx-helia-rt", "nsx-npu")


def test_unknown_template_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(NSXConfigError, match="Unknown app template"):
        create_app_impl(tmp_path / "app", template="does-not-exist")


def test_default_template_renders_hello_world(tmp_path: Path) -> None:
    app_dir = tmp_path / "hello"
    create_app_impl(app_dir, board="apollo510_evb", no_bootstrap=True)

    assert (app_dir / "src" / "main.c").is_file()
    cmake = (app_dir / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "NSX_HELIA_RT_ENABLE_ETHOSU" not in cmake

    manifest = yaml.safe_load((app_dir / "nsx.yml").read_text(encoding="utf-8"))
    assert manifest["modules"] == []


def test_npu_tflm_template_renders_and_seeds_modules(tmp_path: Path) -> None:
    app_dir = tmp_path / "npu_app"
    create_app_impl(
        app_dir,
        board="atomiq110_fpga_turbo",
        no_bootstrap=True,
        template="npu-tflm",
    )

    main = (app_dir / "src" / "main.cc").read_text(encoding="utf-8")
    assert "nsx_npu_init" in main
    assert "AddEthosU" in main
    assert 'section(".sram_bss")' in main

    cmake = (app_dir / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "NSX_HELIA_RT_ENABLE_ETHOSU" in cmake
    assert "nsx::npu" in cmake
    assert "nsx::helia_rt" in cmake

    assert (app_dir / "src" / "model_data.h").is_file()
    assert (app_dir / "tools" / "tflite_to_header.py").is_file()

    manifest = yaml.safe_load((app_dir / "nsx.yml").read_text(encoding="utf-8"))
    declared = [entry["name"] for entry in manifest["modules"]]
    assert declared == ["nsx-helia-rt", "nsx-npu"]
