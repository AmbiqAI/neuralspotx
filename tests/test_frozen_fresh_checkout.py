"""``--frozen`` on a fresh checkout: missing fetchable modules (#289).

Apps keep fetched modules out of git, so a fresh clone has an empty
``modules/``. ``--frozen`` must fetch those at the locked revision and
verify them strictly, while still refusing to touch a module that is
present but differs from the lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from neuralspotx import NSXIntegrityError, module_registry
from neuralspotx.nsx_lock import LockKind, ResolvedModule, hash_tree
from neuralspotx.operations import _sync
from neuralspotx.operations._sync import _sync_fetchable_entry, _SyncContext

_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _write_tree(dest: Path, content: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "src.c").write_text(content, encoding="utf-8")


def _locked_hash(tmp_path: Path, content: str) -> str:
    reference = tmp_path / "reference"
    _write_tree(reference, content)
    return hash_tree(reference)


def _entry(content_hash: str, *, commit: str | None = _COMMIT) -> ResolvedModule:
    return ResolvedModule(
        project="demo-proj",
        kind=LockKind.GIT,
        constraint="v1.0.0",
        vendored_at="modules/demo-proj",
        content_hash=content_hash,
        acquired_at="2026-10-18T00:00:00+00:00",
        url="https://example.com/demo.git",
        commit=commit,
    )


def _ctx(app_dir: Path, *, frozen: bool) -> _SyncContext:
    return _SyncContext(
        app_dir=app_dir,
        registry={},
        cmake_nsx=app_dir / "cmake" / "nsx",
        frozen=frozen,
        force=False,
    )


def _fake_vendor(monkeypatch: pytest.MonkeyPatch, vendored_dir: Path, content: str) -> list[str]:
    """Replace the git fetch with one that writes ``content`` at the vendored path."""

    calls: list[str] = []

    def _vendor(app_dir: Path, name: str, registry: dict[str, Any], commit: str, **_: Any) -> None:  # noqa: ARG001
        calls.append(commit)
        _write_tree(vendored_dir, content)

    monkeypatch.setattr(module_registry, "_vendor_git_module_at_commit", _vendor)
    return calls


def test_frozen_fetches_missing_module_at_locked_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")
    vendored_paths: set[Path] = set()

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, vendored_paths
    )

    assert changed == 1
    assert calls == [_COMMIT]
    assert hash_tree(vendored_dir) == entry.content_hash
    assert vendored_dir in vendored_paths


def test_frozen_removes_fetched_module_that_does_not_match_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    _fake_vendor(monkeypatch, vendored_dir, "upstream moved")

    with pytest.raises(NSXIntegrityError, match="fetched at its locked revision") as excinfo:
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert excinfo.value.module == "demo-mod"
    assert not vendored_dir.exists()


def test_frozen_refuses_present_module_that_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    _write_tree(vendored_dir, "hand patched")
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    with pytest.raises(NSXIntegrityError, match="does not match nsx.lock") as excinfo:
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert excinfo.value.module == "demo-mod"
    assert calls == []
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "hand patched"


def test_frozen_refuses_missing_git_module_without_locked_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"), commit=None)
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    with pytest.raises(NSXIntegrityError, match="records no commit"):
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert calls == []
    assert not vendored_dir.exists()


def test_unfrozen_keeps_mismatched_fetch_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: without --frozen a drifted upstream is kept with a warning."""

    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    _fake_vendor(monkeypatch, vendored_dir, "upstream moved")
    # Record the warning directly: the nsx logger's propagation depends on
    # which CLI tests ran earlier in the session, so caplog is not reliable.
    warnings: list[str] = []
    monkeypatch.setattr(_sync._log, "warning", lambda msg, *args: warnings.append(msg % args))

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=False), "demo-mod", entry, vendored_dir, set()
    )

    assert changed == 1
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "upstream moved"
    assert any("has drifted since lock" in w for w in warnings)
