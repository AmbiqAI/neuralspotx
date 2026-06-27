"""Friendly-failure / typed-error mediation hardening.

The CLI mediator only translates ``NSXError`` and
``subprocess.CalledProcessError`` into friendly exits, and library
embedders catch ``NSXError``. These tests pin the boundaries that were
hardened so that subprocess and lock-parse failures surface as typed
errors on *both* surfaces (CLI and programmatic) rather than leaking a
raw ``FileNotFoundError`` / ``OSError`` / ``yaml.YAMLError`` traceback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neuralspotx import NSXLockError, NSXToolchainError, subprocess_utils
from neuralspotx.nsx_lock import lock_path, read_lock, read_lock_file

# ---------------------------------------------------------------------------
# Subprocess: a missing executable is a typed NSXToolchainError, not a raw
# FileNotFoundError, for both the streaming and captured runners.
# ---------------------------------------------------------------------------

_MISSING = "nsx-definitely-not-a-real-command-xyz"


def test_run_missing_command_raises_toolchain_error() -> None:
    with pytest.raises(NSXToolchainError) as excinfo:
        subprocess_utils.run([_MISSING, "--version"])
    assert _MISSING in str(excinfo.value)


def test_run_capture_missing_command_raises_toolchain_error() -> None:
    with pytest.raises(NSXToolchainError) as excinfo:
        subprocess_utils.run_capture([_MISSING, "--version"])
    assert _MISSING in str(excinfo.value)


# ---------------------------------------------------------------------------
# Lock parse: a corrupt nsx.lock (e.g. unresolved merge-conflict markers)
# raises a typed NSXLockError, not a raw yaml.YAMLError.
# ---------------------------------------------------------------------------


def test_read_lock_file_on_merge_conflict_raises_lock_error(tmp_path: Path) -> None:
    lock_path(tmp_path).write_text(
        "<<<<<<< HEAD\nschema_version: 1\n=======\nschema_version: 2\n>>>>>>> other\n",
        encoding="utf-8",
    )
    with pytest.raises(NSXLockError):
        read_lock_file(tmp_path)


def test_read_lock_on_non_mapping_root_raises_lock_error(tmp_path: Path) -> None:
    lock_path(tmp_path).write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(NSXLockError):
        read_lock(tmp_path)


def test_read_lock_file_missing_returns_none(tmp_path: Path) -> None:
    # The friendly path: no lock at all is not an error.
    assert read_lock_file(tmp_path) is None
