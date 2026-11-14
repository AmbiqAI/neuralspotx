"""Exercise generated probe targets without a probe or a SEGGER installation."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from neuralspotx.subprocess_utils import extract_view_command


@pytest.mark.parametrize("device", [None, "", "   "])
def test_invalid_device_disables_reconfigured_probe_targets(tmp_path: Path, device: str | None):
    for tool in ("cmake", "ninja"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} required")
    helper = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake/nsx_helpers.cmake"
    marker = tmp_path / "probe-called"
    fake = tmp_path / ("probe.bat" if sys.platform == "win32" else "probe")
    if sys.platform == "win32":
        fake.write_text(f'@echo off\necho called>>"{marker}"\n', encoding="utf-8")
    else:
        fake.write_text(f'#!/bin/sh\nprintf called >> "{marker}"\n', encoding="utf-8")
        fake.chmod(0o755)
    build = tmp_path / "build"
    source = tmp_path / "CMakeLists.txt"
    prefix = (
        "cmake_minimum_required(VERSION 3.20)\nproject(probe_test NONE)\n"
        f'set(NSX_CMAKE_DIR "{helper.parent.as_posix()}")\n'
        f'include("{helper.as_posix()}")\nadd_custom_target(demo)\n'
        "set(NSX_SEGGER_IF_SPEED 4000)\nset(NSX_SEGGER_PF_ADDR 0x00410000)\n"
        "set(NSX_SEGGER_CPUFREQ 48000000)\nset(NSX_SEGGER_SWOFREQ 1000000)\n"
    )
    configure = [
        "cmake",
        "-S",
        str(tmp_path),
        "-B",
        str(build),
        "-G",
        "Ninja",
        f"-DNSX_JLINK_EXE={fake.as_posix()}",
        f"-DNSX_JLINK_SWO_EXE={fake.as_posix()}",
        "-DNSX_SEGGER_DEVICE=CachedOldDevice",
    ]
    # Positive control: a valid device invokes the fake tools for all operations.
    source.write_text(prefix + "nsx_add_segger_targets(demo)\n", encoding="utf-8")
    subprocess.run(configure, check=True, capture_output=True, text=True)
    for action in ("flash", "reset", "view"):
        subprocess.run(
            ["cmake", "--build", str(build), "--target", f"demo_{action}"],
            check=True,
            capture_output=True,
            text=True,
        )
    assert marker.read_text().count("called") == 3
    marker.unlink()
    assert (build / "jlink/demo/flash_cmds.jlink").exists()
    # A custom board clears an inherited cached identity, or removes it entirely.
    setting = (
        "unset(NSX_SEGGER_DEVICE CACHE)\nunset(NSX_SEGGER_DEVICE)\n"
        if device is None
        else f'set(NSX_SEGGER_DEVICE "{device}")\n'
    )
    source.write_text(prefix + setting + "nsx_add_segger_targets(demo)\n", encoding="utf-8")
    result = subprocess.run(configure, check=True, capture_output=True, text=True)
    assert "NSX_SEGGER_DEVICE is missing or empty" in result.stderr
    for action in ("flash", "reset", "view"):
        result = subprocess.run(
            ["cmake", "--build", str(build), "--target", f"demo_{action}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "rerun nsx configure" in result.stdout + result.stderr
    if sys.platform != "win32":
        # The CLI runs the extracted viewer argv directly, without a shell.
        result = subprocess.run(
            extract_view_command(build, "demo_view"), capture_output=True, text=True
        )
        assert result.returncode != 0
        assert "rerun nsx configure" in result.stderr
    assert not marker.exists()
    assert not (build / "jlink/demo/flash_cmds.jlink").exists()
    assert not (build / "jlink/demo/reset_cmds.jlink").exists()
