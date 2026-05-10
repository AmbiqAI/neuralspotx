"""Shared helpers for the ``operations`` sub-package.

Holds module-level state (``VERBOSE``), enums, name helpers, the
build-context resolver, and the vendored-module scaffolder. Every
other ``operations.*`` sub-module imports from here.
"""

from __future__ import annotations

import argparse
import enum
import logging
from pathlib import Path

from ..project_config import _default_build_dir, _resolve_app_context
from ..subprocess_utils import set_verbosity as set_subprocess_verbosity

VERBOSE = 0
_log = logging.getLogger(__name__)


def set_verbosity(level: int) -> None:
    """Set shared operation verbosity for subprocess-facing helpers.

    Args:
        level: Verbosity level from the CLI or programmatic caller.
    """

    global VERBOSE
    VERBOSE = level
    set_subprocess_verbosity(level)


# ---------------------------------------------------------------------------
# Status enums
# ---------------------------------------------------------------------------


class OutdatedStatus(str, enum.Enum):
    """Per-module status emitted by ``nsx outdated``.

    Mixed with ``str`` so callers comparing against the legacy
    ``"up-to-date"`` / ``"outdated"`` spellings keep working.
    """

    UP_TO_DATE = "up-to-date"
    OUTDATED = "outdated"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


class ProfileStatus(str, enum.Enum):
    """Profile lifecycle marker stored in ``nsx.yml``.

    ``ACTIVE`` — profile is fully supported.
    ``SCAFFOLD`` — profile exists but build bring-up may be incomplete.
    """

    ACTIVE = "active"
    SCAFFOLD = "scaffold"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


def _module_package_name(module_name: str) -> str:
    """Convert a module name into its default CMake package/header stem."""

    return module_name.replace("-", "_")


def _module_target_name(module_name: str) -> str:
    """Convert a module name into its default namespaced CMake target."""

    stem = _module_package_name(module_name)
    if stem.startswith("nsx_"):
        stem = stem[4:]
    return f"nsx::{stem}"


def _scaffold_vendored_module(target_dir: Path, module_name: str) -> None:
    """Drop minimal ``nsx-module.yaml`` + ``CMakeLists.txt`` into *target_dir*.

    Existing files are left untouched so the helper is idempotent and
    safe to run on a partially-populated module directory.
    """

    metadata_path = target_dir / "nsx-module.yaml"
    if not metadata_path.exists():
        metadata_path.write_text(
            "schema_version: 1\n"
            "module:\n"
            f"  name: {module_name}\n"
            "  type: app\n"
            f'  description: "Vendored module {module_name}"\n'
            "support:\n"
            "  ambiqsuite: true\n"
            "compatibility:\n"
            '  boards: ["*"]\n'
            '  socs: ["*"]\n'
            '  toolchains: ["*"]\n'
            "depends:\n"
            "  required: []\n",
            encoding="utf-8",
        )
    cmake_path = target_dir / "CMakeLists.txt"
    if not cmake_path.exists():
        cmake_path.write_text(
            f"# {module_name} — vendored module (committed in this app).\n"
            f"# Add sources / link libraries below; re-run `nsx lock` after edits.\n"
            f"add_library({module_name} INTERFACE)\n"
            f"target_include_directories({module_name} INTERFACE ${{CMAKE_CURRENT_SOURCE_DIR}})\n",
            encoding="utf-8",
        )


def _resolve_build_context(
    app_dir: Path,
    *,
    board: str | None = None,
    build_dir: Path | None = None,
) -> tuple[Path, str, str, Path]:
    """Resolve the app, board, and build directory for a build-like action."""

    resolved_app_dir, _, app_name, resolved_board = _resolve_app_context(
        argparse.Namespace(app_dir=str(app_dir), board=board)
    )
    resolved_build_dir = build_dir or _default_build_dir(resolved_app_dir, resolved_board)
    return resolved_app_dir, app_name, resolved_board, resolved_build_dir
