"""Tests for ``nsx clean --reset`` purge semantics."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from neuralspotx._errors import NSXError
from neuralspotx.operations._build import clean_app_impl


def _make_app(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    app.mkdir()
    (app / "nsx.yml").write_text("name: dummy\n")
    return app


def test_reset_removes_build_dirs_modules_and_lock(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    (app / "build").mkdir()
    (app / "build" / "stale.txt").write_text("x")
    (app / "build_armclang").mkdir()
    (app / "build_atfe").mkdir()
    modules = app / "modules"
    modules.mkdir()
    (modules / "nsx-core").mkdir()
    (modules / "nsx-core" / "CMakeLists.txt").write_text("# pinned\n")
    lock = app / ".nsx" / "sync.lock"
    lock.parent.mkdir(exist_ok=True)
    lock.write_text("")
    # Bring lock mtime forward so synced module files are not flagged dirty.
    os.utime(lock, None)

    clean_app_impl(app, reset=True)

    assert not (app / "build").exists()
    assert not (app / "build_armclang").exists()
    assert not (app / "build_atfe").exists()
    assert not modules.exists()
    assert not lock.exists()
    # The app itself and its manifest are preserved.
    assert (app / "nsx.yml").exists()


def test_reset_refuses_when_modules_dirty(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    modules = app / "modules" / "nsx-core"
    modules.mkdir(parents=True)
    pinned = modules / "CMakeLists.txt"
    pinned.write_text("# pinned\n")
    lock = app / ".nsx" / "sync.lock"
    lock.parent.mkdir(exist_ok=True)
    lock.write_text("")
    # Backdate the lock so the pinned file is "newer" => dirty.
    old = lock.stat().st_mtime - 60
    os.utime(lock, (old, old))

    with pytest.raises(NSXError, match="Refusing to reset"):
        clean_app_impl(app, reset=True)

    # Nothing was removed.
    assert pinned.exists()
    assert lock.exists()


def test_reset_force_overrides_dirty_check(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    modules = app / "modules" / "nsx-core"
    modules.mkdir(parents=True)
    (modules / "CMakeLists.txt").write_text("# locally edited\n")
    lock = app / ".nsx" / "sync.lock"
    lock.parent.mkdir(exist_ok=True)
    lock.write_text("")
    old = lock.stat().st_mtime - 60
    os.utime(lock, (old, old))

    clean_app_impl(app, reset=True, force=True)

    assert not (app / "modules").exists()
    assert not lock.exists()


def test_reset_without_nsx_yml_fails(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="nsx.yml"):
        clean_app_impl(tmp_path, reset=True)


def test_reset_treats_missing_lock_as_dirty(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    modules = app / "modules" / "nsx-core"
    modules.mkdir(parents=True)
    (modules / "file.txt").write_text("hi")

    with pytest.raises(NSXError, match="Refusing to reset"):
        clean_app_impl(app, reset=True)
