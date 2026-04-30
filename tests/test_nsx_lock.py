"""Unit tests for the NSX lock mechanism.

Covers `nsx lock`, `nsx lock --check`, `nsx sync --frozen`, `nsx outdated --json`,
and `nsx module add --vendored` scaffolding behaviour, across all five lock
``kind`` values (``vendored``, ``local``, ``packaged``, ``git``, ``unresolved``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import operations
from neuralspotx.nsx_lock import LegacyLockError, ResolutionError, read_lock
from neuralspotx.operations import (
    add_module_impl,
    lock_app_impl,
    outdated_app_impl,
    sync_app_impl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_GIT_PROJECT_OVERRIDES: dict[str, Any] = {
    "projects": {
        "fake-proj": {
            "url": "https://example.com/fake.git",
            "revision": "main",
            "path": "modules/fake-proj",
        }
    },
    "modules": {
        "fake-mod": {
            "project": "fake-proj",
            "revision": "main",
            "metadata": "modules/fake-proj/nsx-module.yaml",
        }
    },
}


def _write_nsx_yml(
    app_dir: Path,
    modules: list[dict[str, Any]] | None = None,
    registry_overrides: dict[str, Any] | None = None,
) -> None:
    cfg: dict[str, Any] = {
        "schema_version": 1,
        "project": {"name": "testapp"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "modules": modules or [],
    }
    if registry_overrides:
        cfg["module_registry"] = registry_overrides
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False))


def _make_vendored(app_dir: Path, name: str, content: str = "hi") -> None:
    """Create a vendored module dir with one file."""
    mod = app_dir / "modules" / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "hello.txt").write_text(content)


@pytest.fixture
def app(tmp_path: Path) -> Path:
    """Empty app dir; tests fill in `nsx.yml` + `modules/` as needed."""
    return tmp_path


# ---------------------------------------------------------------------------
# Vendored kind
# ---------------------------------------------------------------------------


class TestVendoredKind:
    def test_lock_records_vendored(self, app: Path) -> None:
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        assert "my-vend" in lock.modules
        m = lock.modules["my-vend"]
        assert m.kind == "vendored"
        assert m.constraint == "vendored"
        assert m.content_hash.startswith("sha256:")
        assert m.commit is None

    def test_check_clean_passes(self, app: Path) -> None:
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        # No mutations -> --check should not raise.
        lock_app_impl(app, check=True)

    def test_check_detects_content_drift(self, app: Path) -> None:
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        # Mutate vendored content -> hash diverges.
        (app / "modules" / "my-vend" / "hello.txt").write_text("CHANGED")

        with pytest.raises(SystemExit) as exc:
            lock_app_impl(app, check=True)
        assert exc.value.code == 1

    def test_check_detects_added_module(self, app: Path) -> None:
        _make_vendored(app, "v1")
        _write_nsx_yml(app, [{"name": "v1", "source": {"vendored": True}}])
        lock_app_impl(app)

        _make_vendored(app, "v2", "b")
        _write_nsx_yml(
            app,
            [
                {"name": "v1", "source": {"vendored": True}},
                {"name": "v2", "source": {"vendored": True}},
            ],
        )
        with pytest.raises(SystemExit) as exc:
            lock_app_impl(app, check=True)
        assert exc.value.code == 1

    def test_check_detects_removed_module(self, app: Path) -> None:
        _make_vendored(app, "v1")
        _make_vendored(app, "v2", "b")
        _write_nsx_yml(
            app,
            [
                {"name": "v1", "source": {"vendored": True}},
                {"name": "v2", "source": {"vendored": True}},
            ],
        )
        lock_app_impl(app)

        _write_nsx_yml(app, [{"name": "v1", "source": {"vendored": True}}])
        with pytest.raises(SystemExit) as exc:
            lock_app_impl(app, check=True)
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Sync --frozen
# ---------------------------------------------------------------------------


class TestSyncFrozen:
    def test_frozen_clean_passes(self, app: Path) -> None:
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        sync_app_impl(app, frozen=True)  # must not raise

    def test_frozen_drift_raises(self, app: Path) -> None:
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        (app / "modules" / "my-vend" / "hello.txt").write_text("MUTATED")

        with pytest.raises(SystemExit):
            sync_app_impl(app, frozen=True)

    def test_no_lock_sync_then_frozen_passes(self, app: Path) -> None:
        """Sync from a fresh tree (no nsx.lock) then `--frozen` sync is a no-op.

        Regression for the bug where ``sync_app_impl`` generated the
        lock *before* vendoring (recording empty-tree content hashes),
        leaving the lock immediately stale: the next ``sync --frozen``
        would fail and every subsequent plain sync would re-vendor. The
        fix is a post-sync lock refresh in the fresh-lock branch.
        """
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])

        assert not (app / "nsx.lock").exists()
        sync_app_impl(app)  # generates lock + syncs + refreshes lock
        assert (app / "nsx.lock").exists()

        sync_app_impl(app, frozen=True)  # must not raise


# ---------------------------------------------------------------------------
# Local kind
# ---------------------------------------------------------------------------


class TestLocalKind:
    def test_lock_records_local(self, app: Path, tmp_path: Path) -> None:
        ext = tmp_path / "ext-source"
        ext.mkdir()
        (ext / "src.c").write_text("// local source")
        (ext / "nsx-module.yaml").write_text("schema_version: 1\n")

        _write_nsx_yml(app, [{"name": "my-local", "source": {"path": str(ext)}}])
        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["my-local"]
        assert m.kind == "local"
        assert m.content_hash.startswith("sha256:")

    def test_lock_local_without_registry_entry(self, app: Path) -> None:
        """`nsx module add --local` writes `local: true` with no registry override.

        Regression for the case where ``_build_lock_for_app`` invoked
        ``registry_entry_for_module`` before the local-name short-circuit
        and raised ``ValueError`` for unknown modules.
        """
        mod_dir = app / "modules" / "bare-local"
        mod_dir.mkdir(parents=True)
        (mod_dir / "src.c").write_text("// local")

        _write_nsx_yml(app, [{"name": "bare-local", "local": True}])

        lock_app_impl(app)  # must not raise

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["bare-local"]
        assert m.kind == "local"
        assert m.constraint == "local"
        assert m.content_hash.startswith("sha256:")


# ---------------------------------------------------------------------------
# Git + Unresolved kinds (monkeypatched resolver)
# ---------------------------------------------------------------------------


class TestGitKind:
    def test_git_lock_records_commit(self, app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_sha = "a" * 40
        monkeypatch.setattr(operations, "resolve_ref", lambda url, ref: (fake_sha, "branch"))

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["fake-mod"]
        assert m.kind == "git"
        assert m.commit == fake_sha
        assert m.url == "https://example.com/fake.git"

    def test_unresolved_when_resolver_fails(
        self, app: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail(url: str, ref: str) -> str:
            raise ResolutionError("offline")

        monkeypatch.setattr(operations, "resolve_ref", _fail)

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["fake-mod"]
        assert m.kind == "unresolved"
        assert m.commit is None

    def test_legacy_v1_lock_migrates_in_place(
        self, app: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A v1 nsx.lock on disk must not block ``nsx lock`` from regenerating."""

        fake_sha = "d" * 40
        monkeypatch.setattr(operations, "resolve_ref", lambda url, ref: (fake_sha, "branch"))

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )

        # Drop a synthetic v1 lock with a legacy `ref` field.
        legacy = {
            "schema_version": 1,
            "generated_at": "2025-01-01T00:00:00+00:00",
            "manifest": {"path": "nsx.yml", "hash": "sha256:deadbeef"},
            "modules": {
                "fake-mod": {
                    "project": "fake-proj",
                    "kind": "git",
                    "constraint": "main",
                    "resolved": {
                        "url": "https://example.com/fake.git",
                        "ref": "main",
                        "commit": "a" * 40,
                        "vendored_at": "modules/fake-mod",
                        "content_hash": "sha256:" + "0" * 64,
                        "acquired_at": "2025-01-01T00:00:00+00:00",
                    },
                }
            },
        }
        (app / "nsx.lock").write_text(yaml.safe_dump(legacy), encoding="utf-8")

        # Strict reads still raise so callers like sync/outdated fail loudly.
        with pytest.raises(LegacyLockError):
            read_lock(app)

        # `nsx lock` rewrites in place under v2.
        lock_app_impl(app)
        capsys.readouterr()

        lock = read_lock(app)
        assert lock is not None
        assert lock.schema_version == 2
        assert lock.modules["fake-mod"].commit == fake_sha
        assert lock.modules["fake-mod"].tag is None


# ---------------------------------------------------------------------------
# Outdated --json
# ---------------------------------------------------------------------------


class TestOutdatedJson:
    def _setup_locked_at(
        self,
        app: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        sha: str,
    ) -> None:
        monkeypatch.setattr(operations, "resolve_ref", lambda url, ref: (sha, "branch"))
        monkeypatch.setattr(operations, "resolve_commit", lambda url, ref: sha)
        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        lock_app_impl(app)
        capsys.readouterr()  # drain lock's stdout

    def test_outdated_when_upstream_advances(
        self,
        app: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        locked = "a" * 40
        upstream = "b" * 40
        self._setup_locked_at(app, monkeypatch, capsys, locked)

        # Upstream "moves".
        monkeypatch.setattr(operations, "resolve_commit", lambda url, ref: upstream)

        rc = outdated_app_impl(app, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert payload["outdated_count"] == 1
        entry = payload["checked"][0]
        assert entry["module"] == "fake-mod"
        assert entry["status"] == "outdated"
        assert entry["locked"] == locked
        assert entry["upstream"] == upstream
        assert entry["url"] == "https://example.com/fake.git"

    def test_up_to_date_when_upstream_matches(
        self,
        app: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        sha = "c" * 40
        self._setup_locked_at(app, monkeypatch, capsys, sha)

        rc = outdated_app_impl(app, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["outdated_count"] == 0
        assert payload["checked"][0]["status"] == "up-to-date"

    def test_non_git_kinds_are_skipped(
        self,
        app: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_vendored(app, "v1")
        _write_nsx_yml(app, [{"name": "v1", "source": {"vendored": True}}])
        lock_app_impl(app)
        capsys.readouterr()  # drain lock's stdout

        rc = outdated_app_impl(app, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["outdated_count"] == 0
        assert payload["checked"] == []


# ---------------------------------------------------------------------------
# Packaged-kind drift regression
# ---------------------------------------------------------------------------


class TestPackagedDriftRegression:
    """Regenerating the packaged tree before hashing makes re-lock idempotent.

    Pre-fix, hashing the on-disk packaged tree before the regenerate step in
    ``_build_lock_for_app`` could surface drift on every re-lock.  This pins
    the post-fix behaviour: a clean lock followed by ``lock --check`` must
    succeed, with the recorded ``content_hash`` unchanged.
    """

    def _pick_packaged_module(self) -> str:
        from neuralspotx.project_config import _load_registry

        reg = _load_registry()
        for name, entry in reg.get("modules", {}).items():
            if isinstance(entry, dict) and entry.get("project") == "neuralspotx":
                return name
        pytest.skip("no packaged modules in registry")

    def test_relock_check_clean(self, app: Path) -> None:
        mod = self._pick_packaged_module()
        _write_nsx_yml(app, [{"name": mod}])

        lock_app_impl(app)
        first = read_lock(app)
        assert first is not None
        first_hash = first.modules[mod].content_hash
        assert first.modules[mod].kind == "packaged"

        # Re-lock --check: the regenerate-before-hash step must keep the
        # tree byte-identical to what we just locked.
        lock_app_impl(app, check=True)

        second = read_lock(app)
        assert second is not None
        assert second.modules[mod].content_hash == first_hash


# ---------------------------------------------------------------------------
# `nsx module add --vendored` scaffold
# ---------------------------------------------------------------------------


class TestAddVendoredModule:
    def test_scaffolds_files_and_updates_nsx_yml(self, app: Path) -> None:
        _write_nsx_yml(app)

        add_module_impl(app, "my-aot", vendored=True)

        m_dir = app / "modules" / "my-aot"
        assert (m_dir / "nsx-module.yaml").exists()
        assert (m_dir / "CMakeLists.txt").exists()

        cfg = yaml.safe_load((app / "nsx.yml").read_text())
        names = [m["name"] for m in cfg["modules"]]
        assert "my-aot" in names
        entry = next(m for m in cfg["modules"] if m["name"] == "my-aot")
        assert entry["source"]["vendored"] is True

    def test_gitignore_does_not_ignore_vendored_dir(self, app: Path) -> None:
        _write_nsx_yml(app)
        add_module_impl(app, "my-aot", vendored=True)

        gitignore = (app / "modules" / ".gitignore").read_text()
        # The vendored module name must NOT appear as an active ignore line
        # (it may appear as a comment for clarity).
        for raw in gitignore.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            assert line != "my-aot/", "vendored module incorrectly added to active gitignore lines"

    def test_refreshes_existing_lock(self, app: Path) -> None:
        _write_nsx_yml(app)
        lock_app_impl(app)  # produce empty lock

        add_module_impl(app, "my-aot", vendored=True)

        lock = read_lock(app)
        assert lock is not None
        assert "my-aot" in lock.modules
        assert lock.modules["my-aot"].kind == "vendored"

    def test_dry_run_does_not_write(self, app: Path) -> None:
        _write_nsx_yml(app)

        add_module_impl(app, "my-aot", vendored=True, dry_run=True)

        assert not (app / "modules" / "my-aot").exists()
        cfg = yaml.safe_load((app / "nsx.yml").read_text())
        assert cfg["modules"] in (None, [])
