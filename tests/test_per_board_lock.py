"""Per-board committed locks for multi-target apps.

Single-target apps keep the legacy unsuffixed ``nsx.lock``; apps with an
explicit ``targets:`` block key their committed lock per board as
``nsx.<board>.lock`` so each target stays independently reproducible.
"""

from __future__ import annotations

from pathlib import Path

from neuralspotx.models import AppConfig, ResolvedTarget
from neuralspotx.nsx_lock import NsxLock, lock_path, read_lock, write_lock
from neuralspotx.nsx_lock._constants import LOCK_SCHEMA_VERSION
from neuralspotx.operations._lock import _apply_active_target, _lock_boards_for
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


# --- lock orchestration: board set + active-target pinning ----------------


def _write_multi_target_manifest(app_dir: Path) -> None:
    (app_dir / "nsx.yml").write_text(
        "schema_version: 1\n"
        "project:\n  name: demo\n"
        "targets:\n"
        "  default: apollo510b_evb\n"
        "  supported: [apollo510_evb, apollo510b_evb]\n",
        encoding="utf-8",
    )


def test_lock_boards_for_single_target_is_legacy(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 1\nproject:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
        encoding="utf-8",
    )
    # Single-target -> one entry, the legacy ``None`` board key.
    assert _lock_boards_for(tmp_path, None) == [None]


def test_lock_boards_for_multi_target_lists_all_default_first(tmp_path: Path) -> None:
    _write_multi_target_manifest(tmp_path)
    # No explicit board -> every supported board, default first.
    assert _lock_boards_for(tmp_path, None) == ["apollo510b_evb", "apollo510_evb"]


def test_lock_boards_for_explicit_board_is_singleton(tmp_path: Path) -> None:
    _write_multi_target_manifest(tmp_path)
    assert _lock_boards_for(tmp_path, "apollo510_evb") == ["apollo510_evb"]


def test_apply_active_target_pins_board_without_mutating_input() -> None:
    cfg = {"target": {"board": "apollo510_evb", "soc": "apollo510"}, "profile": "old"}
    target = ResolvedTarget(
        board="apollo510b_evb",
        soc="apollo510b",
        profile="apollo510b_evb_minimal",
        toolchain="gcc",
    )
    out = _apply_active_target(cfg, target)
    assert out["target"]["board"] == "apollo510b_evb"
    assert out["target"]["soc"] == "apollo510b"
    assert out["profile"] == "apollo510b_evb_minimal"
    assert out["toolchain"] == "gcc"
    # Original config is untouched (deep copy).
    assert cfg["target"]["board"] == "apollo510_evb"
    assert cfg["profile"] == "old"
    assert "toolchain" not in cfg


def test_apply_active_target_derives_soc_from_board_descriptor() -> None:
    # Lean ``targets:`` list entries leave the SoC implicit (soc=None);
    # the active-target injection must derive it from the board descriptor
    # so the downstream closure resolver sees a complete target.
    cfg: dict = {"project": {"name": "demo"}}
    target = ResolvedTarget(board="apollo510b_evb", soc=None)
    out = _apply_active_target(cfg, target)
    assert out["target"]["board"] == "apollo510b_evb"
    assert out["target"]["soc"] == "apollo510b"


# --- additive `requires` merge -------------------------------------------


def _multi_cfg_with_requires() -> dict:
    return {
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {
            "default": "apollo510_evb",
            "supported": {
                "apollo510_evb": {"requires": ["nsx-ambiq-usb"]},
                "apollo510b_evb": {},
            },
        },
        "requires": ["nsx-usb", "nsx-timer"],
    }


def test_resolve_target_merges_global_and_per_target_requires() -> None:
    app = AppConfig.from_mapping(_multi_cfg_with_requires())

    names_a = [r.name for r in app.resolve_target("apollo510_evb").requires]
    names_b = [r.name for r in app.resolve_target("apollo510b_evb").requires]

    # Global first (in order), then this board's per-target extras.
    assert names_a == ["nsx-usb", "nsx-timer", "nsx-ambiq-usb"]
    # The other board only gets the global set.
    assert names_b == ["nsx-usb", "nsx-timer"]


def test_apply_active_target_writes_merged_requires() -> None:
    app = AppConfig.from_mapping(_multi_cfg_with_requires())
    cfg = _multi_cfg_with_requires()

    out = _apply_active_target(cfg, app.resolve_target("apollo510_evb"))

    assert [r["name"] for r in out["requires"]] == ["nsx-usb", "nsx-timer", "nsx-ambiq-usb"]


def test_apply_active_target_clears_requires_when_target_has_none() -> None:
    cfg = _multi_cfg_with_requires()
    # A board with no extras and no global set would clear the key; here we
    # simulate by stripping the global list before resolving the bare board.
    cfg_no_global = dict(cfg)
    cfg_no_global.pop("requires")
    app_no_global = AppConfig.from_mapping(cfg_no_global)

    out = _apply_active_target(cfg_no_global, app_no_global.resolve_target("apollo510b_evb"))

    assert "requires" not in out
