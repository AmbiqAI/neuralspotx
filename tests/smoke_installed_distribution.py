"""Smoke-test an installed neuralspotx wheel without importing the checkout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    """Scaffold and validate a module using only the installed distribution."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--module-dir", type=Path, required=True)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
