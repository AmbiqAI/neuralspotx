"""Per-board committed locks for multi-target apps.

Single-target apps keep the legacy unsuffixed ``nsx.lock``; apps with an
explicit ``targets:`` block key their committed lock per board as
``nsx.<board>.lock`` so each target stays independently reproducible.
"""

from __future__ import annotations

from pathlib import Path

from neuralspotx.models import AppConfig
from neuralspotx.nsx_lock import NsxLock, lock_path, read_lock, write_lock
from neuralspotx.nsx_lock._constants import LOCK_SCHEMA_VERSION
from neuralspotx.project_config import _board_key_for_app, _lock_board_key

# --- lock_path ------------------------------------------------------------


def test_lock_path_single_target_is_legacy_name() -> None:
    app = Path("/tmp/app")
    assert lock_path(app) == app / "nsx.lock"
    assert lock_path(app, None) == app / "nsx.lock"


def test_lock_path_per_board_is_suffixed() -> None:
    app = Path("/tmp/app")
    assert lock_path(app, "apollo510_evb") == app / "nsx.apollo510_evb.lock"
    assert lock_path(app, "apollo510b_evb") == app / "nsx.apollo510b_evb.lock"


# --- is_multi_target / _lock_board_key -----------------------------------


def _multi_cfg() -> dict:
    return {
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {
            "default": "apollo510_evb",
            "supported": ["apollo510_evb", "apollo510b_evb"],
        },
    }


def _single_cfg() -> dict:
    return {
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": "apollo510_evb"},
    }


def test_single_target_is_not_multi_target() -> None:
    assert AppConfig.from_mapping(_single_cfg()).is_multi_target() is False


def test_targets_block_is_multi_target() -> None:
    assert AppConfig.from_mapping(_multi_cfg()).is_multi_target() is True


def test_lock_board_key_single_target_is_none() -> None:
    # Single-target apps always map to the legacy unsuffixed lock.
    assert _lock_board_key(_single_cfg()) is None
    assert _lock_board_key(_single_cfg(), "apollo510_evb") is None


def test_lock_board_key_multi_target_defaults_to_default_board() -> None:
    assert _lock_board_key(_multi_cfg()) == "apollo510_evb"


def test_lock_board_key_multi_target_honours_explicit_board() -> None:
    assert _lock_board_key(_multi_cfg(), "apollo510b_evb") == "apollo510b_evb"


# --- _board_key_for_app (manifest-tolerant) ------------------------------


def test_board_key_for_app_missing_manifest_falls_back_to_legacy(tmp_path: Path) -> None:
    # No nsx.yml on disk -> read-only callers fall back to nsx.lock.
    assert _board_key_for_app(tmp_path) is None


def test_board_key_for_app_reads_multi_target_manifest(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 1\n"
        "project:\n  name: demo\n"
        "targets:\n"
        "  default: apollo510_evb\n"
        "  supported: [apollo510_evb, apollo510b_evb]\n",
        encoding="utf-8",
    )
    assert _board_key_for_app(tmp_path) == "apollo510_evb"
    assert _board_key_for_app(tmp_path, "apollo510b_evb") == "apollo510b_evb"


# --- write/read round-trip keyed per board -------------------------------


def _empty_lock() -> NsxLock:
    return NsxLock(
        schema_version=LOCK_SCHEMA_VERSION,
        generated_at="2026-01-01T00:00:00Z",
        nsx_tool_version="0.0.0",
        manifest_path="nsx.yml",
        manifest_hash="deadbeef",
        target={"board": "apollo510_evb"},
        modules={},
    )


def test_per_board_locks_are_independent_files(tmp_path: Path) -> None:
    write_lock(tmp_path, _empty_lock(), "apollo510_evb")
    write_lock(tmp_path, _empty_lock(), "apollo510b_evb")

    assert (tmp_path / "nsx.apollo510_evb.lock").exists()
    assert (tmp_path / "nsx.apollo510b_evb.lock").exists()
    assert not (tmp_path / "nsx.lock").exists()

    assert read_lock(tmp_path, "apollo510_evb") is not None
    assert read_lock(tmp_path, "apollo510b_evb") is not None
    # The legacy unsuffixed lock is absent for a multi-target app.
    assert read_lock(tmp_path) is None
