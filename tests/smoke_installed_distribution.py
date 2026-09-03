"""Smoke-test an installed neuralspotx wheel without importing the checkout."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import yaml

# Files every ``create-app --no-bootstrap`` scaffold must ship, per template.
# The npu-tflm entries guard the wheel-level package-data contract: the
# template renders fine from a checkout (``pip install -e``) even when a file
# is missing from ``[tool.setuptools.package-data]``, so only a real wheel
# proves it. ``.gitignore`` is the canary for the dotfile glob (``**/*``
# never matches leading-dot names).
_EXPECTED_APP_FILES: dict[str, tuple[str, ...]] = {
    "default": (".gitignore",),
    "npu-tflm": (
        ".gitignore",
        "src/main.cc",
        "src/model_data.h",
        "tools/tflite_to_header.py",
        "cmake/presets/CMakePresets.json",
        "nsx.yml",
    ),
}
_TEMPLATE_BOARDS: dict[str, str] = {
    "default": "apollo510_evb",
    "npu-tflm": "atomiq110_fpga_turbo",
}
_SPDX_HEADER = "SPDX-License-Identifier: BSD-3-Clause"
_COPYRIGHT_HEADER = "Copyright (c) 2026, Ambiq"
_PACKAGED_SOURCE_SUFFIXES = {".cmake", ".in", ".yaml"}


def _smoke_create_app(nsx_main: Callable[[list[str]], int], work_dir: Path, template: str) -> None:
    """Scaffold *template* with ``--no-bootstrap`` and check its shipped files."""

    app_dir = work_dir / f"wheel-smoke-app-{template}"
    result = nsx_main([
        "create-app",
        str(app_dir),
        "--board",
        _TEMPLATE_BOARDS[template],
        "--template",
        template,
        "--no-bootstrap",
    ])
    if result != 0:
        raise RuntimeError(f"nsx create-app --template {template} failed with exit code {result}")
    missing = [rel for rel in _EXPECTED_APP_FILES[template] if not (app_dir / rel).is_file()]
    if missing:
        raise RuntimeError(
            f"create-app --template {template} scaffold is missing packaged template files: "
            + json.dumps(missing)
        )


def _smoke_packaged_licenses(package_dir: Path) -> None:
    """Verify every registry-backed packaged module in the installed wheel."""

    registry_path = package_dir / "data" / "registry.lock.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    package_prefix = Path("src/neuralspotx")
    roots: list[Path] = []

    for name, entry in registry["modules"].items():
        if entry.get("project") != "neuralspotx":
            continue
        metadata = Path(entry["metadata"])
        try:
            relative_metadata = metadata.relative_to(package_prefix)
        except ValueError as exc:
            raise RuntimeError(
                f"Packaged module {name!r} has metadata outside {package_prefix}: {metadata}"
            ) from exc
        root = package_dir / relative_metadata.parent
        if not root.is_dir():
            raise RuntimeError(f"Packaged module {name!r} is missing from the wheel: {root}")
        roots.append(root)

    if not roots:
        raise RuntimeError("Installed registry contains no neuralspotx packaged modules")

    license_texts: set[str] = set()
    missing_headers: list[str] = []
    for root in roots:
        license_path = root / "LICENSE"
        if not license_path.is_file():
            raise RuntimeError(f"Packaged module is missing LICENSE: {root}")
        license_texts.add(license_path.read_text(encoding="utf-8"))

        sources = sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in _PACKAGED_SOURCE_SUFFIXES
        )
        for source in sources:
            prefix = "// " if source.name.endswith(".jlink.in") else "# "
            expected = [prefix + _SPDX_HEADER, prefix + _COPYRIGHT_HEADER]
            lines = source.read_text(encoding="utf-8").splitlines()
            if lines[:2] != expected:
                missing_headers.append(source.relative_to(package_dir).as_posix())

    if len(license_texts) != 1:
        raise RuntimeError("Packaged modules do not carry one identical project license")
    if not next(iter(license_texts)).startswith("BSD 3-Clause License\n"):
        raise RuntimeError("Packaged module LICENSE is not the BSD 3-Clause project license")
    if missing_headers:
        raise RuntimeError(
            "Packaged wheel sources are missing leading BSD-3-Clause headers: "
            + json.dumps(missing_headers)
        )


def main() -> int:
    """Scaffold and validate a module and app templates using only the installed distribution."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--module-dir", type=Path, required=True)
    parser.add_argument(
        "--app-work-dir",
        type=Path,
        default=None,
        help="Directory to scaffold the create-app smoke apps into (default: a temp dir)",
    )
    args = parser.parse_args()

    import neuralspotx
    from neuralspotx.cli import main as nsx_main

    package_path = Path(neuralspotx.__file__).resolve()
    install_root = args.install_root.resolve()
    if not package_path.is_relative_to(install_root):
        raise RuntimeError(
            f"Expected neuralspotx to load from {install_root}, loaded {package_path} instead"
        )

    _smoke_packaged_licenses(package_path.parent)

    init_result = nsx_main([
        "module",
        "init",
        str(args.module_dir),
        "--name",
        "wheel-smoke-module",
        "--summary",
        "Installed wheel smoke-test module",
    ])
    if init_result != 0:
        raise RuntimeError(f"nsx module init failed with exit code {init_result}")

    metadata_path = args.module_dir / "nsx-module.yaml"
    validate_result = nsx_main(["module", "validate", str(metadata_path), "--json"])
    if validate_result != 0:
        raise RuntimeError(f"nsx module validate failed with exit code {validate_result}")

    expected_files = {
        "CMakeLists.txt",
        "README.md",
        "includes-api/wheel_smoke_module/wheel_smoke_module.h",
        "nsx-module.yaml",
        "src/wheel_smoke_module.c",
    }
    actual_files = {
        path.relative_to(args.module_dir).as_posix()
        for path in args.module_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise RuntimeError(
            "Generated module files differ from the expected skeleton: "
            + json.dumps(
                {
                    "missing": sorted(expected_files - actual_files),
                    "unexpected": sorted(actual_files - expected_files),
                },
                sort_keys=True,
            )
        )

    # App templates: no-network (--no-bootstrap) scaffold of every packaged
    # template against the wheel, so a template file dropped by package-data
    # fails here instead of for every pipx user.
    if args.app_work_dir is not None:
        args.app_work_dir.mkdir(parents=True, exist_ok=True)
        for template in _EXPECTED_APP_FILES:
            _smoke_create_app(nsx_main, args.app_work_dir, template)
    else:
        with tempfile.TemporaryDirectory(prefix="nsx-wheel-apps-") as tmp:
            for template in _EXPECTED_APP_FILES:
                _smoke_create_app(nsx_main, Path(tmp), template)
    return 0


if __name__ == "__main__":
    sys.exit(main())
