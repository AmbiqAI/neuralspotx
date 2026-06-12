"""CMake-level contract for ``nsx_module_dir_for_name``.

The app bootstrap resolves each module's vendored directory through
``nsx_module_dir_for_name``. A consolidated SDK bundle (e.g.
``nsx-ambiq-sdk``) nests its modules under the project dir, so the
generated ``cmake/nsx/modules.cmake`` emits ``NSX_APP_MODULE_DIR_<id>``
overrides that must win over the flat ``modules/<name>`` default.

Regression guard for the bootstrap fix that made the override resolve
reliably: ``nsx_module_dir_for_name`` first honours the override variable
when it is visible in scope and otherwise falls back to the directory-scope
``DEFINITION`` lookup before defaulting. These tests drive the real packaged
CMake via ``cmake -P`` script mode, so they exercise the helper end to end
without a firmware build or toolchain.
"""

from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

CMAKE = shutil.which("cmake")

pytestmark = pytest.mark.skipif(CMAKE is None, reason="cmake not available")


def _bootstrap_cmake(tmp_path: Path) -> Path:
    """Copy the packaged bootstrap script into *tmp_path* and return it."""
    dest = tmp_path / "cmake"
    dest.mkdir(exist_ok=True)
    pkg = resources.files("neuralspotx.cmake")
    src = pkg.joinpath("nsx_app_bootstrap.cmake")
    with resources.as_file(src) as path:
        target = dest / "nsx_app_bootstrap.cmake"
        target.write_text(Path(path).read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _resolve(
    tmp_path: Path, *, module_name: str, override: str | None
) -> subprocess.CompletedProcess[str]:
    """Invoke ``nsx_module_dir_for_name(module_name)`` via cmake script mode."""
    bootstrap = _bootstrap_cmake(tmp_path)
    lines = []
    if override is not None:
        var = "NSX_APP_MODULE_DIR_" + module_name.replace("-", "_")
        lines.append(f'set({var} "{override}")')
    lines += [
        f'include("{bootstrap.as_posix()}")',
        f'nsx_module_dir_for_name(resolved "{module_name}")',
        'message(STATUS "RESOLVED_MODULE_DIR=${resolved}")',
    ]
    harness = tmp_path / "harness.cmake"
    harness.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subprocess.run(
        [CMAKE, "-P", str(harness)],
        capture_output=True,
        text=True,
    )


def test_override_wins_over_default(tmp_path: Path) -> None:
    """A NSX_APP_MODULE_DIR_<id> override resolves the nested SDK path."""
    result = _resolve(
        tmp_path,
        module_name="nsx-core",
        override="modules/nsx-ambiq-sdk/modules/nsx-core",
    )

    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "RESOLVED_MODULE_DIR=modules/nsx-ambiq-sdk/modules/nsx-core" in out


def test_dashed_module_name_maps_to_underscore_override(tmp_path: Path) -> None:
    """Hyphenated module names map to the underscored override variable."""
    result = _resolve(
        tmp_path,
        module_name="nsx-freertos",
        override="modules/nsx-ambiq-sdk/modules/nsx-freertos",
    )

    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "RESOLVED_MODULE_DIR=modules/nsx-ambiq-sdk/modules/nsx-freertos" in out


def test_default_layout_when_no_override(tmp_path: Path) -> None:
    """Without an override the helper falls back to the flat layout."""
    result = _resolve(tmp_path, module_name="nsx-core", override=None)

    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "RESOLVED_MODULE_DIR=modules/nsx-core" in out
