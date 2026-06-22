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
        "schema_version": 2,
        "project": {"name": "demo"},
        "targets": {
            "default": "apollo510_evb",
            "supported": ["apollo510_evb", "apollo510b_evb"],
        },
    }


def _single_cfg() -> dict:
    return {
        "schema_version": 2,
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
        "schema_version: 2\n"
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
        "schema_version: 2\n"
        "project:\n  name: demo\n"
        "targets:\n"
        "  default: apollo510b_evb\n"
        "  supported: [apollo510_evb, apollo510b_evb]\n",
        encoding="utf-8",
    )


def test_lock_boards_for_single_target_is_legacy(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
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


# --- additive per-board module scoping -----------------------------------
# The old additive ``requires:`` field (global + per-target merge) was removed
# in schema v2. Per-board dependency scoping is now expressed with a ``boards:``
# filter on a ``modules:`` entry and applied by ``expand_profile_seeds`` when a
# board is pinned; that behavior is covered in test_profile_seeded_resolution.py.
# ``_apply_active_target`` itself only pins the target and no longer rewrites
# dependencies, so the former requires-merge tests no longer apply.


# --- board-switch glue regeneration --------------------------------------


def test_write_text_if_changed_skips_identical_content(tmp_path: Path) -> None:
    from neuralspotx.project_config import _write_text_if_changed

    target = tmp_path / "modules.cmake"

    assert _write_text_if_changed(target, "one\n") is True
    mtime = target.stat().st_mtime_ns

    # Identical content must not rewrite (keeps mtime stable for
    # CMake CONFIGURE_DEPENDS).
    assert _write_text_if_changed(target, "one\n") is False
    assert target.stat().st_mtime_ns == mtime

    # Changed content rewrites.
    assert _write_text_if_changed(target, "two\n") is True
    assert target.read_text(encoding="utf-8") == "two\n"


def test_regenerate_active_board_glue_uses_active_board_module_set(
    tmp_path: Path, monkeypatch
) -> None:
    import neuralspotx.operations._sync as sync_mod

    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\n"
        "project:\n  name: demo\n"
        "targets:\n"
        "  default: apollo510_evb\n"
        "  supported: [apollo510_evb, apollo4p_blue_kxr_evb]\n",
        encoding="utf-8",
    )

    class _FakeLock:
        def __init__(self, names: list[str]) -> None:
            # Ordered mapping keyed by module name (mirrors NsxLock.modules).
            self.modules = {name: object() for name in names}

    locks = {
        "apollo510_evb": _FakeLock(["nsx-core", "nsx-pmu-armv8m"]),
        "apollo4p_blue_kxr_evb": _FakeLock(["nsx-core"]),
    }
    monkeypatch.setattr(sync_mod, "read_lock", lambda _app, board_key: locks.get(board_key))
    monkeypatch.setattr(sync_mod, "_load_registry", lambda: {})
    monkeypatch.setattr(sync_mod, "expand_profile_seeds", lambda cfg, _reg: cfg)

    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(
        sync_mod,
        "_write_app_module_file",
        lambda _app, _cfg, module_names: captured.__setitem__("modules", list(module_names)),
    )
    monkeypatch.setattr(
        sync_mod,
        "_write_modules_gitignore_for_module_names",
        lambda _app, _cfg, names: captured.__setitem__("gitignore", list(names)),
    )

    # Switching to Apollo4 must regenerate glue from the Apollo4 lock, not
    # leak the Apollo5-only nsx-pmu-armv8m from the Apollo510 lock.
    sync_mod.regenerate_active_board_glue(tmp_path, "apollo4p_blue_kxr_evb")

    assert captured["modules"] == ["nsx-core"]
    assert captured["gitignore"] == ["nsx-core"]
    assert "nsx-pmu-armv8m" not in captured["modules"]


def test_regenerate_active_board_glue_is_noop_without_lock(tmp_path: Path, monkeypatch) -> None:
    import neuralspotx.operations._sync as sync_mod

    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_mod, "read_lock", lambda _app, _board_key: None)

    called = {"write": False}
    monkeypatch.setattr(
        sync_mod,
        "_write_app_module_file",
        lambda *a, **k: called.__setitem__("write", True),
    )

    # No lock yet -> the full sync path owns creation; regen must not write.
    sync_mod.regenerate_active_board_glue(tmp_path, "apollo510_evb")
    assert called["write"] is False
