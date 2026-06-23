"""Tests for the CLI developer-experience improvements:

* ``lock_freshness_warning`` — flag locks that track moving refs and are old.
* app-name discovery in ``resolve_app_dir`` / ``discover_apps`` so commands
  work from a repository root holding many app subdirectories.
* ``format_subprocess_error`` — surface captured output on failure instead of
  forcing a re-run under ``--verbose``.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from neuralspotx.nsx_lock import LockKind, NsxLock, ResolvedModule, write_lock
from neuralspotx.operations import lock_freshness_warning
from neuralspotx.project_config import discover_apps, resolve_app_dir
from neuralspotx.subprocess_utils import format_subprocess_error


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _lock_with_module(generated_at: str, module: ResolvedModule) -> NsxLock:
    return NsxLock(
        generated_at=generated_at,
        nsx_tool_version="0.0.0",
        manifest_path="nsx.yml",
        manifest_hash="sha256:" + "0" * 64,
        target={"board": "apollo510_evb", "toolchain": "gcc"},
        modules={module.project: module},
    )


def _git_module(
    constraint: str, *, tag: str | None = None, commit: str = "a" * 40
) -> ResolvedModule:
    return ResolvedModule(
        project="nsx-dep",
        kind=LockKind.GIT,
        constraint=constraint,
        vendored_at="modules/nsx-dep",
        content_hash="sha256:" + "a" * 64,
        acquired_at="2026-01-01T00:00:00+00:00",
        url="https://example.com/nsx-dep.git",
        tag=tag,
        commit=commit,
    )


class TestLockFreshnessWarning:
    def test_no_lock_returns_none(self, tmp_path: Path) -> None:
        assert lock_freshness_warning(tmp_path) is None

    def test_stale_moving_ref_warns(self, tmp_path: Path) -> None:
        write_lock(tmp_path, _lock_with_module(_iso_days_ago(30), _git_module("main")))
        note = lock_freshness_warning(tmp_path)
        assert note is not None
        assert "nsx update" in note
        assert "nsx-dep" in note

    def test_recent_moving_ref_is_quiet(self, tmp_path: Path) -> None:
        write_lock(tmp_path, _lock_with_module(_iso_days_ago(1), _git_module("main")))
        assert lock_freshness_warning(tmp_path) is None

    def test_pinned_sha_is_quiet(self, tmp_path: Path) -> None:
        sha = "b" * 40
        write_lock(tmp_path, _lock_with_module(_iso_days_ago(30), _git_module(sha, commit=sha)))
        assert lock_freshness_warning(tmp_path) is None

    def test_tagged_ref_is_quiet(self, tmp_path: Path) -> None:
        write_lock(
            tmp_path,
            _lock_with_module(_iso_days_ago(30), _git_module("v1.2.3", tag="v1.2.3")),
        )
        assert lock_freshness_warning(tmp_path) is None

    def test_threshold_env_disables(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_LOCK_STALE_DAYS", "0")
        write_lock(tmp_path, _lock_with_module(_iso_days_ago(30), _git_module("main")))
        assert lock_freshness_warning(tmp_path) is None


class TestAppDiscovery:
    def _make_app(self, root: Path, name: str) -> Path:
        app = root / name
        app.mkdir(parents=True)
        (app / "nsx.yml").write_text("project:\n  name: " + name + "\n", encoding="utf-8")
        return app

    def test_discover_apps_finds_direct_and_examples(self, tmp_path: Path) -> None:
        self._make_app(tmp_path, "top_app")
        self._make_app(tmp_path / "examples", "hello_world")
        apps = discover_apps(tmp_path)
        assert apps["top_app"] == (tmp_path / "top_app").resolve()
        assert apps["hello_world"] == (tmp_path / "examples" / "hello_world").resolve()

    def test_resolve_app_dir_by_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        app = self._make_app(tmp_path / "examples", "hello_world")
        monkeypatch.chdir(tmp_path)
        assert resolve_app_dir("hello_world") == app.resolve()

    def test_resolve_app_dir_existing_path_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app = self._make_app(tmp_path, "myapp")
        monkeypatch.chdir(tmp_path)
        assert resolve_app_dir("myapp") == app.resolve()

    def test_resolve_app_dir_unknown_name_passthrough(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        # No such app — the value is returned as a path for a clear
        # downstream "nsx.yml not found" error.
        assert resolve_app_dir("nope") == (tmp_path / "nope").resolve()


class TestFormatSubprocessError:
    def test_includes_captured_output(self) -> None:
        exc = subprocess.CalledProcessError(
            2, ["cmake", "--build", "."], output="line one\nfatal error: boom\n", stderr=""
        )
        message = format_subprocess_error(exc, context="Build")
        assert "Build failed" in message
        assert "fatal error: boom" in message

    def test_no_output_keeps_verbose_hint(self) -> None:
        exc = subprocess.CalledProcessError(2, ["cmake"], output="", stderr="")
        message = format_subprocess_error(exc, context="Build")
        assert "Re-run with `--verbose`" in message
