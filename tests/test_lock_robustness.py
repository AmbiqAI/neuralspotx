"""Tests for nsx_lock.py write_lock atomicity, lock --check read-only behaviour,
and the per-app advisory file lock used to serialise concurrent ``nsx``
invocations against the same app.

These exercises target the robustness fixes in ``fix/nsx-lock-correctness``:
the prior implementation wrote ``nsx.lock`` non-atomically, ``nsx lock --check``
silently regenerated build glue (``cmake/nsx/``, ``modules.cmake``,
``modules/.gitignore``), and there was no inter-process lock around
``sync``/``lock``/``update``.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import pytest

from neuralspotx import NSXError
from neuralspotx.file_lock import AppLockBusyError, app_lock, app_lock_path
from neuralspotx.nsx_lock import NsxLock, ResolvedModule, write_lock

# ---------------------------------------------------------------------------
# write_lock — atomicity
# ---------------------------------------------------------------------------


class TestWriteLockAtomic:
    def _make_lock(self) -> NsxLock:
        return NsxLock(
            generated_at="2026-01-01T00:00:00+00:00",
            nsx_tool_version="0.0.0",
            manifest_path="nsx.yml",
            manifest_hash="sha256:" + "0" * 64,
            target={"toolchain": "gcc"},
            modules={
                "fake": ResolvedModule(
                    project="fake",
                    kind="vendored",
                    constraint="vendored",
                    vendored_at="modules/fake",
                    content_hash="sha256:" + "a" * 64,
                    acquired_at="2026-01-01T00:00:00+00:00",
                )
            },
        )

    def test_write_lock_round_trips(self, tmp_path: Path) -> None:
        path = write_lock(tmp_path, self._make_lock())
        assert path == tmp_path / "nsx.lock"
        text = path.read_text(encoding="utf-8")
        assert "schema_version" in text
        assert "fake" in text

    def test_write_lock_replaces_existing_atomically(self, tmp_path: Path) -> None:
        # Pre-populate with a sentinel; write_lock must replace it
        # without leaving a half-written tmp file behind.
        (tmp_path / "nsx.lock").write_text("# stale\n", encoding="utf-8")
        write_lock(tmp_path, self._make_lock())

        siblings = list(tmp_path.iterdir())
        # Only nsx.lock should remain — no nsx.lock.*.tmp leftovers.
        assert siblings == [tmp_path / "nsx.lock"]
        text = (tmp_path / "nsx.lock").read_text(encoding="utf-8")
        assert "# stale" not in text
        assert "fake" in text

    def test_write_lock_cleans_tmp_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If os.replace raises, the temp file must be cleaned up."""

        real_replace = os.replace

        def boom(_src: str, _dst: str) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError, match="simulated"):
            write_lock(tmp_path, self._make_lock())
        # No lockfile, no leftover *.tmp.
        assert list(tmp_path.iterdir()) == []
        # Sanity-check the monkeypatch is gone (avoid masking other tests).
        monkeypatch.setattr(os, "replace", real_replace)


# ---------------------------------------------------------------------------
# app_lock — per-app advisory lock
# ---------------------------------------------------------------------------


class TestAppLock:
    def test_creates_lockfile_in_app_dir(self, tmp_path: Path) -> None:
        with app_lock(tmp_path):
            assert app_lock_path(tmp_path).exists()
        # File is left in place after release; only the OS-level lock is dropped.
        assert app_lock_path(tmp_path).exists()

    def test_reentrant_in_same_process(self, tmp_path: Path) -> None:
        # Nested acquisition of the same app dir must not deadlock.
        with app_lock(tmp_path):
            with app_lock(tmp_path):
                with app_lock(tmp_path):
                    pass

    def test_independent_apps_do_not_block(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        with app_lock(a):
            # Holding A's lock must not block B's lock.
            with app_lock(b, blocking=False):
                pass

    def test_non_blocking_raises_when_busy(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("cross-process lock probe via fork is POSIX-only")
        # Cross-process busy probe: acquire the lock in a child, then try
        # non-blocking from the parent.
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        release = ctx.Event()

        def hold_lock(app_dir: str) -> None:
            with app_lock(Path(app_dir)):
                ready.set()
                release.wait(timeout=10)

        p = ctx.Process(target=hold_lock, args=(str(tmp_path),))
        p.start()
        try:
            assert ready.wait(timeout=5), "child failed to acquire lock"
            with pytest.raises(AppLockBusyError):
                with app_lock(tmp_path, blocking=False):
                    pass
        finally:
            release.set()
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

    def test_blocking_waits_for_release(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip("cross-process lock probe via fork is POSIX-only")
        ctx = multiprocessing.get_context("fork")
        ready = ctx.Event()
        release = ctx.Event()

        def hold_lock(app_dir: str) -> None:
            with app_lock(Path(app_dir)):
                ready.set()
                release.wait(timeout=10)

        p = ctx.Process(target=hold_lock, args=(str(tmp_path),))
        p.start()
        try:
            assert ready.wait(timeout=5), "child failed to acquire lock"
            # Schedule release in 0.4s; blocking acquire should wait then succeed.
            t0 = time.monotonic()
            ctx2 = multiprocessing.get_context("fork")
            releaser = ctx2.Process(
                target=lambda: (time.sleep(0.4), release.set()) and None,
            )
            releaser.start()
            with app_lock(tmp_path):
                elapsed = time.monotonic() - t0
            releaser.join(timeout=5)
            assert elapsed >= 0.3, f"blocking acquire returned too quickly ({elapsed:.2f}s)"
        finally:
            release.set()
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()


# ---------------------------------------------------------------------------
# nsx lock --check is read-only
# ---------------------------------------------------------------------------


class TestLockCheckReadOnly:
    """``nsx lock --check`` must never mutate the on-disk app.

    The pre-fix code unconditionally regenerated ``cmake/nsx/``,
    ``modules.cmake``, and ``modules/.gitignore`` inside
    ``_build_lock_for_app`` — which made ``--check`` mutate files even
    though it documented itself as read-only.
    """

    def test_check_does_not_create_build_glue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx import operations
        from neuralspotx.operations import lock_app_impl

        app = tmp_path / "app"
        app.mkdir()
        (app / "nsx.yml").write_text("modules: []\n", encoding="utf-8")

        # No nsx.lock yet -> --check must report a (trivial) drift and
        # exit non-zero, but it must not have written cmake/nsx/ or
        # modules.cmake along the way.
        monkeypatch.chdir(app)
        with pytest.raises(NSXError):
            lock_app_impl(app, check=True)

        # The point of the test: read-only mode created none of the
        # build-glue side-effect files.
        assert not (app / "cmake" / "nsx").exists(), (
            "lock --check leaked cmake/nsx/ on read-only run"
        )
        assert not (app / "modules.cmake").exists(), (
            "lock --check leaked modules.cmake on read-only run"
        )
        assert not (app / "modules" / ".gitignore").exists(), (
            "lock --check leaked modules/.gitignore on read-only run"
        )
        # Sanity: operations module was actually imported (not a typo).
        assert hasattr(operations, "lock_app_impl")
