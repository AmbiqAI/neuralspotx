"""No-network tests for ``create-app`` template selection."""

from __future__ import annotations

import glob
import tomllib
from pathlib import Path

import pytest
import yaml

import neuralspotx
from neuralspotx._errors import NSXConfigError
from neuralspotx.operations import APP_TEMPLATES, create_app_impl

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(neuralspotx.__file__).resolve().parent


def test_app_templates_registry_shape() -> None:
    assert "default" in APP_TEMPLATES
    assert "npu-tflm" in APP_TEMPLATES
    assert APP_TEMPLATES["default"].modules == ()
    assert APP_TEMPLATES["npu-tflm"].modules == ("nsx-helia-rt", "nsx-npu")


def _package_data_files() -> set[Path]:
    """Every package-relative file the ``neuralspotx`` package-data globs select.

    Mirrors setuptools' ``build_py.find_data_files``, which expands each
    ``[tool.setuptools.package-data]`` pattern with
    ``glob.glob(..., recursive=True)`` relative to the package directory.
    Using ``glob`` itself (rather than ``fnmatch``) keeps the exact quirks:
    ``**`` spans zero or more directories, and a ``*`` never matches a
    leading-dot name, so dotfiles need their own pattern.
    """

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"]["neuralspotx"]
    matched: set[Path] = set()
    for pattern in patterns:
        for hit in glob.glob(pattern, root_dir=PACKAGE_DIR, recursive=True):
            if (PACKAGE_DIR / hit).is_file():
                matched.add(Path(hit))
    return matched


def _template_dirs() -> list[Path]:
    """Every template directory under the package, not just ``APP_TEMPLATES``.

    Module skeletons and any template added later are covered too, so a new
    directory is checked the moment it exists on disk.
    """

    return sorted(
        path
        for path in (PACKAGE_DIR / "templates").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    )


def test_app_template_files_are_packaged() -> None:
    """Every file of every template directory must ship in the wheel.

    A template directory that is on disk in a checkout but missing from
    ``package-data`` renders fine under ``pip install -e`` and then fails for
    every ``pipx`` user, so the packaging contract is asserted here without
    building a wheel. ``templates/**/*`` covers new directories, but ``**/*``
    never matches dotfiles: a template's ``.gitignore`` relies on the
    separate ``templates/*/.gitignore`` entry, which this test also proves.
    """

    template_dirs = _template_dirs()
    for template in APP_TEMPLATES.values():
        assert PACKAGE_DIR / "templates" / template.template_dir in template_dirs

    # ``templates/**/*`` also matches a checkout's stale
    # ``templates/__pycache__/*.pyc``; the wheel must exclude those.
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excludes = pyproject["tool"]["setuptools"]["exclude-package-data"]["*"]
    assert any("__pycache__" in pattern for pattern in excludes), excludes

    packaged = _package_data_files()
    missing: list[str] = []
    for template_dir in template_dirs:
        name = template_dir.name
        files = sorted(
            path.relative_to(PACKAGE_DIR)
            for path in template_dir.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        assert files, f"{name}: template directory {template_dir} is empty"
        missing.extend(f"{name}: {rel.as_posix()}" for rel in files if rel not in packaged)
    assert not missing, (
        "Template files not selected by any [tool.setuptools.package-data] glob "
        "in pyproject.toml:\n  " + "\n  ".join(missing)
    )


def test_unknown_template_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(NSXConfigError, match="Unknown app template"):
        create_app_impl(tmp_path / "app", template="does-not-exist")


def test_npu_template_refuses_non_npu_board_before_any_write(tmp_path: Path) -> None:
    """``npu-tflm`` on a non-atomiq110 board fails before touching the disk.

    The gate runs right after SoC inference and ahead of template rendering
    and module acquisition, so the app directory must not exist afterwards
    (nothing to roll back) and no network is involved.
    """

    assert APP_TEMPLATES["npu-tflm"].socs == ("atomiq110",)
    assert APP_TEMPLATES["default"].socs == ()

    app_dir = tmp_path / "wrong_board"
    with pytest.raises(NSXConfigError) as excinfo:
        create_app_impl(
            app_dir,
            board="apollo510_evb",
            no_bootstrap=True,
            template="npu-tflm",
        )
    message = str(excinfo.value)
    assert "Template 'npu-tflm' targets SoCs [atomiq110]" in message
    assert "board 'apollo510_evb' is apollo510" in message
    assert "--template default" in message
    assert not app_dir.exists()
    assert list(tmp_path.iterdir()) == []


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
