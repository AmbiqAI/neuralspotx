"""Opt-in cross-repository ARM link test; CI supplies an immutable SDK candidate."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from neuralspotx import api, cli
from neuralspotx._errors import NSXConfigError, NSXIntegrityError
from neuralspotx.api import (
    build_app,
    configure_app,
    create_app,
    create_board,
    flash_app,
    lock_app,
    sync_app,
)


@pytest.mark.parametrize(
    "parent,soc", [("apollo330mP_evb", "apollo330P"), ("apollo510_evb", "apollo510")]
)
def test_custom_bsp_app_links_without_evb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parent: str, soc: str
) -> None:
    sdk = os.environ.get("NSX_TEST_CUSTOM_BSP_SDK")
    if not sdk:
        pytest.skip("Explicit SDK candidate required for cross-repository integration")
    assert shutil.which("arm-none-eabi-gcc"), "ARM compiler required for custom BSP integration"
    root = tmp_path / "custom_probe"
    create_app(root, board=parent, no_bootstrap=True)
    create_board("custom_board", from_board=parent, app_dir=root, bsp_module="test-bsp")
    provider = root / "modules/test-bsp"
    provider.mkdir(parents=True)
    metadata = {
        "schema_version": 1,
        "module": {"name": "test-bsp", "type": "runtime", "version": "1.0.0"},
        "support": {"ambiqsuite": True, "zephyr": False},
        "build": {"cmake": {"package": "test_bsp", "targets": ["nsx::bsp"]}},
        "depends": {"required": ["nsx-ambiq-hal"], "optional": []},
        "compatibility": {
            "boards": ["custom_board"],
            "socs": [soc],
            "toolchains": ["arm-none-eabi-gcc"],
        },
        "contracts": {"provides": {"bsp": {"versions": [2], "socs": [soc]}}},
    }
    (provider / "nsx-module.yaml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    (provider / "CMakeLists.txt").write_text(
        """add_library(test_bsp STATIC bsp.c)
target_include_directories(test_bsp PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(test_bsp PUBLIC nsx_ambiq_hal nsx::board_flags)
nsx_register_bsp(TARGET test_bsp CONTRACT 2 DEBUG_ITM 0 DEBUG_UART 0)
""",
        encoding="utf-8",
    )
    # This is a link-only BSP, not an implementation to flash on hardware.
    (provider / "am_bsp.h").write_text(
        '#include "am_mcu_apollo.h"\nvoid am_bsp_low_power_init(void);\n', encoding="utf-8"
    )
    (provider / "bsp.c").write_text(
        '#include "am_bsp.h"\nvoid am_bsp_low_power_init(void) {}\n', encoding="utf-8"
    )
    (root / "src/main.c").write_text("int main(void) {return 0;}\n", encoding="utf-8")
    config = {
        "schema_version": 2,
        "project": {"name": "custom_probe"},
        "target": {"board": "custom_board", "soc": soc},
        "modules": [{"name": "test-bsp", "source": {"vendored": True}}],
        "module_registry": {
            "projects": {"nsx-ambiq-sdk": {"local_path": str(Path(sdk).resolve())}}
        },
    }
    (root / "nsx.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    cmake = root / "CMakeLists.txt"
    cmake.write_text(
        cmake.read_text(encoding="utf-8").replace(
            "include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_debug_template.cmake)",
            'set(NSX_DEBUG_CONTEXT ON CACHE BOOL "Prepare configured debug handoff")\n'
            "set(NSX_DEBUG_INPUT_CONTRACT 1)\n"
            "include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_debug_template.cmake)",
        )
        + "\ntarget_link_options(custom_probe PRIVATE LINKER:-u,nsx_system_init)\n",
        encoding="utf-8",
    )
    lock = lock_app(root)
    assert "nsx-ambiq-bsp" not in lock.modules
    assert lock.board_composition is not None
    sync_app(root, frozen=True)
    configure_app(root, frozen=True)
    build_app(root, frozen=True)
    build = root / "build/custom_board"
    image = build / "custom_probe"
    assert image.is_file()
    symbols = subprocess.check_output(["arm-none-eabi-nm", str(image)], text=True)
    assert " T am_bsp_low_power_init" in symbols
    assert " T nsx_system_init" in symbols
    ninja = (build / "build.ninja").read_text(encoding="utf-8")
    assert "libam_bsp" not in ninja
    assert f"boards/{parent}/bsp" not in ninja
    guarded_outputs = [image, build / "CMakeCache.txt", build / "build.ninja"]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guarded_outputs}
    # The real custom board has no physical debug configuration. Its current
    # configured target rejects flash (including update) before rebuilding.
    monkeypatch.setattr(api, "update_app", lambda *a, **k: pytest.fail("updated build-only board"))

    with pytest.raises(NSXConfigError, match="FLASH unavailable.*verified board debug settings"):
        flash_app(root, frozen=True)
    assert cli.main(["flash", "--app-dir", str(root), "--update"]) == 1
    assert before == {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guarded_outputs
    }
    manifest = provider / "nsx-module.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n# changed contract input\n", encoding="utf-8"
    )
    # Frozen verification now precedes regeneration/composition validation.
    with pytest.raises(NSXIntegrityError, match="content drifted from lock") as caught:
        build_app(root, frozen=True)
    assert caught.value.module == "test-bsp"
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in guarded_outputs
    } == before
