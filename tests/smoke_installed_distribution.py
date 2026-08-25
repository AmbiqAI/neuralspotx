"""Smoke-test an installed neuralspotx wheel without importing the checkout."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

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


def _smoke_create_app(
    nsx_main: Callable[[list[str]], int], work_dir: Path, template: str
) -> None:
    """Scaffold *template* with ``--no-bootstrap`` and check its shipped files."""

    app_dir = work_dir / f"wheel-smoke-app-{template}"
    result = nsx_main(
        [
            "create-app",
            str(app_dir),
            "--board",
            _TEMPLATE_BOARDS[template],
            "--template",
            template,
            "--no-bootstrap",
        ]
    )
    if result != 0:
        raise RuntimeError(f"nsx create-app --template {template} failed with exit code {result}")
    missing = [rel for rel in _EXPECTED_APP_FILES[template] if not (app_dir / rel).is_file()]
    if missing:
        raise RuntimeError(
            f"create-app --template {template} scaffold is missing packaged template files: "
            + json.dumps(missing)
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

    init_result = nsx_main(
        [
            "module",
            "init",
            str(args.module_dir),
            "--name",
            "wheel-smoke-module",
            "--summary",
            "Installed wheel smoke-test module",
        ]
    )
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
