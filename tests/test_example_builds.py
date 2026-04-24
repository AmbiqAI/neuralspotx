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

    # The build target name matches the directory / project name.
    app_name = example_app.name
    build_dir = example_app / "build" / "apollo510_evb"
    # The executable suffix depends on toolchain (.axf for GCC, .elf for armclang)
    # and may be absent depending on CMake configuration.
    candidates = [
        build_dir / f"{app_name}.axf",
        build_dir / f"{app_name}.elf",
        build_dir / app_name,
    ]
    elf = next((c for c in candidates if c.exists()), None)
    assert elf is not None, f"Expected ELF at {build_dir}/{app_name}[.axf|.elf]"
