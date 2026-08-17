"""E2E build tests for the example applications.

Each test copies an example to *tmp_path*, runs ``nsx configure`` and
``nsx build``, then checks that the output ELF exists.

The tests are skipped automatically when the required cross toolchain
is not on PATH. Set ``NSX_TEST_TOOLCHAIN`` to exercise a non-default
toolchain — supported values are ``arm-none-eabi-gcc`` (default),
``armclang`` (Arm Compiler for Embedded), or ``atfe`` (Arm Toolchain for
Embedded; requires ``ATFE_ROOT`` to be set).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# Discover every sub-directory that contains an nsx.yml.
# Skip examples with a .ci-skip marker (they have external dependencies).
_EXAMPLE_NAMES = sorted(
    d.name
    for d in EXAMPLES_DIR.iterdir()
    if d.is_dir() and (d / "nsx.yml").exists() and not (d / ".ci-skip").exists()
)

_TOOLCHAIN = os.environ.get("NSX_TEST_TOOLCHAIN", "arm-none-eabi-gcc")


def _atfe_clang_path() -> str | None:
    """Return the ATfE clang binary if ``ATFE_ROOT`` is set and valid."""
    root = os.environ.get("ATFE_ROOT")
    if not root:
        return None
    candidate = Path(root) / "bin" / "clang"
    return str(candidate) if candidate.exists() else None


if _TOOLCHAIN == "armclang":
    _HAS_TOOLCHAIN = shutil.which("armclang") is not None
    _PROBE_DESC = "armclang"
elif _TOOLCHAIN == "atfe":
    _HAS_TOOLCHAIN = _atfe_clang_path() is not None
    _PROBE_DESC = "ATfE clang (via ATFE_ROOT)"
else:
    _HAS_TOOLCHAIN = shutil.which("arm-none-eabi-gcc") is not None
    _PROBE_DESC = "arm-none-eabi-gcc"

pytestmark = pytest.mark.skipif(
    not _HAS_TOOLCHAIN,
    reason=f"{_PROBE_DESC} not found — skipping E2E build tests",
)


@pytest.fixture()
def example_app(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Copy the requested example into *tmp_path* and return the app dir."""
    name: str = request.param
    src = EXAMPLES_DIR / name
    if sys.platform == "win32":
        # Windows enforces a 260-char MAX_PATH and CMake caps object paths at
        # 250. pytest's tmp_path is already deeply nested, so combining it with
        # long example/board names (e.g. freertos_blinky_apollo4p /
        # apollo4p_blue_kxr_evb) and the deep vendored SDK tree (e.g.
        # FreeRTOS-Kernel/portable/GCC/ARM_CM55_NTZ/non_secure/...) overflows
        # the limit during vendoring and compilation. Use a short temp root.
        root = Path(tempfile.mkdtemp(prefix="nsx"))
        request.addfinalizer(lambda: shutil.rmtree(root, ignore_errors=True))
        dst = root / name
    else:
        dst = tmp_path / name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("build"))
    return dst


@pytest.mark.parametrize("example_app", _EXAMPLE_NAMES, indirect=True)
def test_example_configures_and_builds(example_app: Path) -> None:
    """``nsx configure`` + ``nsx build`` succeeds for each example."""
    configure_cmd = ["nsx", "configure", "--app-dir", str(example_app)]
    build_cmd = ["nsx", "build", "--app-dir", str(example_app)]
    if _TOOLCHAIN != "arm-none-eabi-gcc":
        configure_cmd += ["--toolchain", _TOOLCHAIN]
        build_cmd += ["--toolchain", _TOOLCHAIN]
    subprocess.run(configure_cmd, check=True, timeout=300)
    subprocess.run(build_cmd, check=True, timeout=300)

    # The build target name matches the directory / project name. The build
    # tree is nested under build/<board>/, where <board> is the example's
    # target board (not necessarily apollo510_evb), so discover it rather
    # than hard-coding a single board.
    app_name = example_app.name
    build_root = example_app / "build"
    build_dirs = [d for d in build_root.iterdir() if d.is_dir()] if build_root.is_dir() else []
    # The executable suffix depends on toolchain (.axf for GCC, .elf for armclang)
    # and may be absent depending on CMake configuration.
    candidates = [
        build_dir / name
        for build_dir in build_dirs
        for name in (f"{app_name}.axf", f"{app_name}.elf", app_name)
    ]
    elf = next((c for c in candidates if c.exists()), None)
    assert elf is not None, (
        f"Expected ELF for {app_name} under {build_root}/<board>/[.axf|.elf]; "
        f"searched board dirs: {[d.name for d in build_dirs]}"
    )

    if app_name == "ble_webble":
        # This example carries a deliberately tiny EXCLUDE_FROM_ALL image so
        # hardware smoke tests can exercise named-target flashing without
        # replacing or complicating the primary BLE application.
        secondary_target = "ble_webble_flash_probe"
        secondary_cmd = [
            "nsx",
            "build",
            "--app-dir",
            str(example_app),
            "--target",
            secondary_target,
        ]
        if _TOOLCHAIN != "arm-none-eabi-gcc":
            secondary_cmd += ["--toolchain", _TOOLCHAIN]
        subprocess.run(secondary_cmd, check=True, timeout=300)

        secondary_artifacts = [
            build_dir / name
            for build_dir in build_dirs
            for name in (
                f"{secondary_target}.bin",
                f"{secondary_target}.axf",
                f"{secondary_target}.elf",
                secondary_target,
            )
        ]
        assert any(path.exists() for path in secondary_artifacts)
        assert any(
            (build_dir / "jlink" / secondary_target / "flash_cmds.jlink").is_file()
            for build_dir in build_dirs
        )
