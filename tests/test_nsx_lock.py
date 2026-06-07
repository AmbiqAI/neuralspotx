"""Unit tests for the NSX lock mechanism.

Covers `nsx lock`, `nsx lock --check`, `nsx sync --frozen`, `nsx outdated --json`,
and `nsx module add --vendored` scaffolding behaviour, across all five lock
``kind`` values (``vendored``, ``local``, ``packaged``, ``git``, ``unresolved``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXError, NSXLockError, NSXResolutionError, operations
from neuralspotx.nsx_lock import (
    LockKind,
    NsxLock,
    ResolutionError,
    ResolvedModule,
    hash_manifest,
    read_lock,
    utcnow_iso,
    write_lock,
)
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
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _make_vendored(app_dir: Path, name: str, content: str = "hi") -> None:
    """Create a vendored module dir with one file."""
    mod = app_dir / "modules" / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "hello.txt").write_text(content, encoding="utf-8")


def _write_local_project_with_nested_nsx(
    root: Path,
    *,
    module_name: str,
    required: list[str] | None = None,
) -> None:
    required = required or []
    nsx_dir = root / "nsx"
    nsx_dir.mkdir(parents=True, exist_ok=True)
    required_lines = [f"    - {name}" for name in required] or ["    []"]
    (nsx_dir / "nsx-module.yaml").write_text(
        "\n".join([
            "schema_version: 1",
            "module:",
            f"  name: {module_name}",
            "  type: runtime",
            '  version: "0.1.0"',
            "support:",
            "  ambiqsuite: true",
            "  zephyr: false",
            "build:",
            "  cmake:",
            f"    package: {module_name.replace('-', '_')}",
            f"    targets: [nsx::{module_name.removeprefix('nsx-').replace('-', '_')} ]",
            "depends:",
            "  required:",
            *required_lines,
            "  optional: []",
            "compatibility:",
            '  boards: ["*"]',
            '  socs: ["*"]',
            '  toolchains: ["arm-none-eabi-gcc"]',
        ])
        + "\n",
        encoding="utf-8",
    )
    (nsx_dir / "CMakeLists.txt").write_text(
        f"add_library({module_name.replace('-', '_')} INTERFACE)\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(f"{module_name}\n", encoding="utf-8")


def _write_fake_git_metadata(app_dir: Path) -> None:
    mod_dir = app_dir / "modules" / "fake-proj"
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "nsx-module.yaml").write_text(
        "\n".join([
            "schema_version: 1",
            "module:",
            "  name: fake-mod",
            "  type: runtime",
            '  version: "0.1.0"',
            "support:",
            "  ambiqsuite: true",
            "  zephyr: false",
            "build:",
            "  cmake:",
            "    package: fake_mod",
            "    targets: [nsx::fake_mod]",
            "depends:",
            "  required: []",
            "  optional: []",
            "compatibility:",
            '  boards: ["*"]',
            '  socs: ["*"]',
            '  toolchains: ["arm-none-eabi-gcc"]',
        ])
        + "\n",
        encoding="utf-8",
    )


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
        (app / "modules" / "my-vend" / "hello.txt").write_text("CHANGED", encoding="utf-8")

        with pytest.raises(NSXError) as exc:
            lock_app_impl(app, check=True)
        assert str(exc.value) == "1"

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
        with pytest.raises(NSXError) as exc:
            lock_app_impl(app, check=True)
        assert str(exc.value) == "1"

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
        with pytest.raises(NSXError) as exc:
            lock_app_impl(app, check=True)
        assert str(exc.value) == "1"


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

        (app / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        with pytest.raises(NSXError):
            sync_app_impl(app, frozen=True)

    def test_no_lock_sync_then_frozen_passes(self, app: Path, tmp_path: Path) -> None:
        """Fresh-checkout flow: ``nsx sync`` with no lock generates one and converges.

        With v3 schema, ``content_hash`` is the upstream-artifact hash
        computed at lock time, so ``nsx lock`` produces correct hashes
        on a fresh tree without ``modules/`` being populated. Sync then
        materializes from the upstream, generating ``nsx.lock`` when it is
        absent, and a later ``--frozen`` sync must not rewrite that lock.
        """
        ext = tmp_path / "ext-source"
        ext.mkdir()
        (ext / "src.c").write_text("// local source", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text("schema_version: 1\n", encoding="utf-8")

        _write_nsx_yml(app, [{"name": "my-local", "source": {"path": str(ext)}}])

        assert not (app / "nsx.lock").exists()
        assert not (app / "modules" / "my-local").exists()

        sync_app_impl(app)
        assert (app / "nsx.lock").exists()
        assert (app / "modules" / "my-local" / "src.c").exists()

        # Lock must not be rewritten by sync; --frozen verifies cleanly.
        before_text = (app / "nsx.lock").read_text(encoding="utf-8")
        sync_app_impl(app, frozen=True)  # must not raise
        assert (app / "nsx.lock").read_text(encoding="utf-8") == before_text

    def test_frozen_does_not_rewrite_lock(self, app: Path) -> None:
        """`sync --frozen` is read-only — it must never write nsx.lock."""
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        lock_path_ = app / "nsx.lock"
        before_mtime = lock_path_.stat().st_mtime_ns
        before_text = lock_path_.read_text(encoding="utf-8")

        sync_app_impl(app, frozen=True)

        assert lock_path_.stat().st_mtime_ns == before_mtime
        assert lock_path_.read_text(encoding="utf-8") == before_text

    def test_noop_sync_does_not_rewrite_lock(self, app: Path) -> None:
        """A no-op `nsx sync` (nothing changed) must not bump nsx.lock."""
        _make_vendored(app, "my-vend")
        _write_nsx_yml(app, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(app)

        lock_path_ = app / "nsx.lock"
        before_text = lock_path_.read_text(encoding="utf-8")

        sync_app_impl(app)  # nothing to do

        assert lock_path_.read_text(encoding="utf-8") == before_text

    def test_sync_never_writes_lock(self, app: Path, tmp_path: Path) -> None:
        """Sync is pure: even when it actively re-vendors, it does not touch nsx.lock.

        Regression for the v2 design where the post-sync lock refresh
        could rewrite the lock under various conditions.
        """
        ext = tmp_path / "ext-source"
        ext.mkdir()
        (ext / "src.c").write_text("// v1", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text("schema_version: 1\n", encoding="utf-8")

        _write_nsx_yml(app, [{"name": "my-local", "source": {"path": str(ext)}}])
        lock_app_impl(app)
        sync_app_impl(app)  # populate modules/

        lock_path_ = app / "nsx.lock"
        before_text = lock_path_.read_text(encoding="utf-8")
        before_mtime = lock_path_.stat().st_mtime_ns

        # Mutate modules/<name>/ so sync has work to do.
        (app / "modules" / "my-local" / "src.c").write_text("// stomped", encoding="utf-8")

        sync_app_impl(app, force=True)

        # Lock must be byte-identical even after a re-vendor.
        assert lock_path_.read_text(encoding="utf-8") == before_text
        assert lock_path_.stat().st_mtime_ns == before_mtime

    def test_sync_detects_local_source_drift(self, app: Path, tmp_path: Path) -> None:
        """Sync must mirror upstream-source changes even when modules/ matches the lock.

        Regression: previously sync compared
        ``hash_tree(modules/<name>/) == entry.content_hash`` to decide
        whether to re-mirror a ``kind=local`` entry whose
        ``content_hash`` is the upstream-source hash. If the source
        had drifted but the on-disk mirror still matched the lock's
        old hash, sync silently skipped re-mirroring and the user
        kept seeing stale source — and ``--frozen`` failed to flag
        the drift.
        """
        ext = tmp_path / "ext-source"
        ext.mkdir()
        (ext / "src.c").write_text("// v1", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text("schema_version: 1\n", encoding="utf-8")

        _write_nsx_yml(app, [{"name": "my-local", "source": {"path": str(ext)}}])
        lock_app_impl(app)
        sync_app_impl(app)
        assert (app / "modules" / "my-local" / "src.c").read_text(encoding="utf-8") == "// v1"

        # Drift the upstream source; the on-disk mirror still matches
        # the lock's recorded content_hash (it's the v1-source hash).
        (ext / "src.c").write_text("// v2", encoding="utf-8")

        # --frozen must surface the upstream drift.
        with pytest.raises(NSXError):
            sync_app_impl(app, frozen=True)

        # A plain sync must update the mirror to match current source.
        sync_app_impl(app)
        assert (app / "modules" / "my-local" / "src.c").read_text(encoding="utf-8") == "// v2"

    def test_local_project_ignores_virtualenv_noise_for_frozen_sync(
        self, app: Path, tmp_path: Path
    ) -> None:
        ext = tmp_path / "ext-proj"
        ext.mkdir()
        (ext / "src.c").write_text("// from local project", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text(
            "\n".join([
                "schema_version: 1",
                "module:",
                "  name: local-mod",
                "  type: runtime",
                '  version: "0.1.0"',
                "support:",
                "  ambiqsuite: true",
                "  zephyr: false",
                "build:",
                "  cmake:",
                "    package: local_mod",
                "    targets: [local_mod]",
                "depends:",
                "  required: []",
                "  optional: []",
                "compatibility:",
                '  boards: ["*"]',
                '  socs: ["*"]',
                '  toolchains: ["arm-none-eabi-gcc"]',
            ])
            + "\n",
            encoding="utf-8",
        )
        (ext / ".venv" / "lib64" / "site.py").parent.mkdir(parents=True)
        (ext / ".venv" / "lib64" / "site.py").write_text("# local venv noise\n", encoding="utf-8")

        _write_nsx_yml(
            app,
            [{"name": "local-mod", "project": "local-proj", "revision": "main"}],
            registry_overrides={
                "projects": {
                    "local-proj": {
                        "local_path": str(ext),
                        "revision": "main",
                        "path": "modules/local-proj",
                    }
                },
                "modules": {
                    "local-mod": {
                        "project": "local-proj",
                        "revision": "main",
                        "metadata": "modules/local-proj/nsx-module.yaml",
                    }
                },
            },
        )

        lock_app_impl(app)
        sync_app_impl(app)
        sync_app_impl(app, frozen=True)
        assert not (app / "modules" / "local-proj" / ".venv").exists()


# ---------------------------------------------------------------------------
# Local kind
# ---------------------------------------------------------------------------


class TestLocalKind:
    def test_lock_records_local(self, app: Path, tmp_path: Path) -> None:
        ext = tmp_path / "ext-source"
        ext.mkdir()
        (ext / "src.c").write_text("// local source", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text("schema_version: 1\n", encoding="utf-8")

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
        (mod_dir / "src.c").write_text("// local", encoding="utf-8")

        _write_nsx_yml(app, [{"name": "bare-local", "local": True}])

        lock_app_impl(app)  # must not raise

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["bare-local"]
        assert m.kind == "local"
        assert m.constraint == "local"
        assert m.content_hash.startswith("sha256:")

    def test_lock_registry_project_local_path_no_url(self, app: Path, tmp_path: Path) -> None:
        """Registry project with ``local_path`` and no ``url`` locks as local.

        Regression for the case where a registry override declares a
        project as a local mirror (e.g. via
        ``nsx module register --project-local-path``) and a module
        entry references that project. Before the fix,
        ``_build_lock_for_app`` raised ``SystemExit('... has no URL in
        registry; cannot lock.')`` even though the project was
        explicitly local-only.
        """
        ext = tmp_path / "ext-proj"
        ext.mkdir()
        (ext / "src.c").write_text("// from local project", encoding="utf-8")
        (ext / "nsx-module.yaml").write_text(
            "\n".join([
                "schema_version: 1",
                "module:",
                "  name: local-mod",
                "  type: runtime",
                '  version: "0.1.0"',
                "support:",
                "  ambiqsuite: true",
                "  zephyr: false",
                "build:",
                "  cmake:",
                "    package: local_mod",
                "    targets: [local_mod]",
                "depends:",
                "  required: []",
                "  optional: []",
                "compatibility:",
                '  boards: ["*"]',
                '  socs: ["*"]',
                '  toolchains: ["arm-none-eabi-gcc"]',
            ])
            + "\n",
            encoding="utf-8",
        )

        # Keep a vendored module dir matching the project's configured
        # ``path`` (modules/local-proj/) so sync-style code paths can
        # find it. The lock ``content_hash`` for this local project is
        # derived from the upstream ``local_path`` (the external
        # source), not from this vendored directory.
        mod_dir = app / "modules" / "local-proj"
        mod_dir.mkdir(parents=True)
        (mod_dir / "src.c").write_text("// from local project", encoding="utf-8")

        _write_nsx_yml(
            app,
            [{"name": "local-mod", "project": "local-proj", "revision": "main"}],
            registry_overrides={
                "projects": {
                    "local-proj": {
                        # No "url" — only a local_path.
                        "local_path": str(ext),
                        "revision": "main",
                        "path": "modules/local-proj",
                    }
                },
                "modules": {
                    "local-mod": {
                        "project": "local-proj",
                        "revision": "main",
                        "metadata": "modules/local-proj/nsx-module.yaml",
                    }
                },
            },
        )

        lock_app_impl(app)  # must not raise "has no URL in registry"

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["local-mod"]
        assert m.kind == "local"
        assert m.constraint == "main"
        # Normalize separators: Windows produces backslashes here.
        assert Path(m.vendored_at).as_posix() == "modules/local-proj"
        assert m.content_hash.startswith("sha256:")

    def test_lock_resolves_transitive_closure_for_nested_module_roots(
        self, app: Path, tmp_path: Path
    ) -> None:
        dep_source = tmp_path / "dep-source"
        app_source = tmp_path / "app-source"
        _write_local_project_with_nested_nsx(dep_source, module_name="nsx-dep")
        _write_local_project_with_nested_nsx(
            app_source,
            module_name="nsx-app",
            required=["nsx-dep"],
        )

        _write_nsx_yml(
            app,
            [{"name": "nsx-app", "project": "app-proj", "revision": "main"}],
            registry_overrides={
                "projects": {
                    "dep-proj": {
                        "local_path": str(dep_source),
                        "revision": "main",
                        "path": "modules/dep-proj",
                    },
                    "app-proj": {
                        "local_path": str(app_source),
                        "revision": "main",
                        "path": "modules/app-proj",
                    },
                },
                "modules": {
                    "nsx-dep": {
                        "project": "dep-proj",
                        "revision": "main",
                        "metadata": "modules/dep-proj/nsx/nsx-module.yaml",
                    },
                    "nsx-app": {
                        "project": "app-proj",
                        "revision": "main",
                        "metadata": "modules/app-proj/nsx/nsx-module.yaml",
                    },
                },
            },
        )

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        assert list(lock.modules) == ["nsx-dep", "nsx-app"]
        nsx_cfg = yaml.safe_load((app / "nsx.yml").read_text(encoding="utf-8"))
        assert [item["name"] for item in nsx_cfg["modules"]] == ["nsx-app"]

        modules_cmake = (app / "cmake" / "nsx" / "modules.cmake").read_text(
            encoding="utf-8"
        )
        assert modules_cmake.index("    nsx-dep") < modules_cmake.index("    nsx-app")
        assert 'set(NSX_APP_MODULE_DIR_nsx_dep "modules/dep-proj/nsx")' in modules_cmake
        assert 'set(NSX_APP_MODULE_DIR_nsx_app "modules/app-proj/nsx")' in modules_cmake

        # Each distinct git-hosted project root is emitted into
        # NSX_APP_PROJECT_DIRS so the app bootstrap can include the
        # project's own cmake/*.cmake helpers (needed for consolidated
        # SDK bundles that vendor many modules under one project dir).
        assert "set(NSX_APP_PROJECT_DIRS" in modules_cmake
        project_dirs_block = modules_cmake.split("set(NSX_APP_PROJECT_DIRS", 1)[1]
        assert "    modules/app-proj" in project_dirs_block
        assert "    modules/dep-proj" in project_dirs_block

        gitignore = (app / "modules" / ".gitignore").read_text(encoding="utf-8")
        assert "dep-proj/" in gitignore
        assert "app-proj/" in gitignore
        assert "nsx-dep/" not in gitignore

    def test_check_uses_locked_closure_when_metadata_not_materialized(self, app: Path) -> None:
        registry_overrides = {
            "projects": {
                "dep-proj": {
                    "url": "https://example.com/dep.git",
                    "revision": "main",
                    "path": "modules/dep-proj",
                },
                "app-proj": {
                    "url": "https://example.com/app.git",
                    "revision": "main",
                    "path": "modules/app-proj",
                },
            },
            "modules": {
                "nsx-dep": {
                    "project": "dep-proj",
                    "revision": "main",
                    "metadata": "modules/dep-proj/nsx-module.yaml",
                },
                "nsx-app": {
                    "project": "app-proj",
                    "revision": "main",
                    "metadata": "modules/app-proj/nsx-module.yaml",
                },
            },
        }
        _write_nsx_yml(
            app,
            [{"name": "nsx-app", "project": "app-proj", "revision": "main"}],
            registry_overrides=registry_overrides,
        )
        now = utcnow_iso()
        write_lock(
            app,
            NsxLock(
                generated_at=now,
                nsx_tool_version="test",
                manifest_hash=hash_manifest(app / "nsx.yml"),
                target={
                    "board": "apollo510_evb",
                    "soc": "apollo510",
                    "toolchain": "arm-none-eabi-gcc",
                },
                modules={
                    "nsx-dep": ResolvedModule(
                        project="dep-proj",
                        kind=LockKind.GIT,
                        constraint="main",
                        vendored_at="modules/dep-proj",
                        content_hash="sha256:" + "d" * 64,
                        acquired_at=now,
                        url="https://example.com/dep.git",
                        commit="d" * 40,
                    ),
                    "nsx-app": ResolvedModule(
                        project="app-proj",
                        kind=LockKind.GIT,
                        constraint="main",
                        vendored_at="modules/app-proj",
                        content_hash="sha256:" + "a" * 64,
                        acquired_at=now,
                        url="https://example.com/app.git",
                        commit="a" * 40,
                    ),
                },
            ),
        )

        lock_app_impl(app, check=True)

        assert not (app / "modules" / "dep-proj").exists()
        assert not (app / "modules" / "app-proj").exists()

    def test_lock_fails_when_dependency_metadata_unavailable(self, app: Path) -> None:
        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )

        with pytest.raises(NSXResolutionError, match="Unable to resolve dependency metadata"):
            lock_app_impl(app)

        assert not (app / "nsx.lock").exists()

    def test_lock_accepts_legacy_registry_metadata_for_dependency_resolution(
        self, app: Path, tmp_path: Path
    ) -> None:
        source = tmp_path / "legacy-source"
        source.mkdir()
        (source / "nsx-module.yaml").write_text(
            "\n".join([
                "schema_version: 1",
                "module:",
                "  name: legacy-mod",
                "  type: runtime",
                '  version: "0.1.0"',
                "support:",
                "  ambiqsuite: true",
                "  zephyr: false",
                "build:",
                "  cmake:",
                "    targets: [nsx::legacy]",
                "depends:",
                "  required: []",
                "  optional: []",
                'socs: ["*"]',
            ])
            + "\n",
            encoding="utf-8",
        )

        _write_nsx_yml(
            app,
            [{"name": "legacy-mod", "project": "legacy-proj", "revision": "main"}],
            registry_overrides={
                "projects": {
                    "legacy-proj": {
                        "local_path": str(source),
                        "revision": "main",
                        "path": "modules/legacy-proj",
                    }
                },
                "modules": {
                    "legacy-mod": {
                        "project": "legacy-proj",
                        "revision": "main",
                        "metadata": "modules/legacy-proj/nsx-module.yaml",
                    }
                },
            },
        )

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        assert list(lock.modules) == ["legacy-mod"]


# ---------------------------------------------------------------------------
# Git + Unresolved kinds (monkeypatched resolver)
# ---------------------------------------------------------------------------


class TestGitKind:
    def test_git_lock_records_commit(self, app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_sha = "a" * 40
        monkeypatch.setattr(operations._lock, "resolve_ref", lambda url, ref: (fake_sha, "branch"))
        monkeypatch.setattr(
            operations._lock,
            "hash_git_artifact",
            lambda url, commit: "sha256:" + "f" * 64,
        )

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        _write_fake_git_metadata(app)

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["fake-mod"]
        assert m.kind == "git"
        assert m.commit == fake_sha
        assert m.url == "https://example.com/fake.git"
        # content_hash is the upstream-artifact hash from
        # hash_git_artifact, not a hash of modules/<name>/.
        assert m.content_hash == "sha256:" + "f" * 64

    def test_git_lock_refreshes_branch_constraints_each_run(
        self, app: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first_sha = "a" * 40
        second_sha = "b" * 40
        seen: list[str] = []

        def _resolve(url: str, ref: str) -> tuple[str, str]:
            seen.append(ref)
            return ((first_sha if len(seen) == 1 else second_sha), "branch")

        monkeypatch.setattr(operations._lock, "resolve_ref", _resolve)
        monkeypatch.setattr(
            operations._lock,
            "hash_git_artifact",
            lambda url, commit: "sha256:" + commit[:1] * 64,
        )

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        _write_fake_git_metadata(app)

        lock_app_impl(app)
        first_lock = read_lock(app)
        assert first_lock is not None
        assert first_lock.modules["fake-mod"].commit == first_sha

        lock_app_impl(app)
        second_lock = read_lock(app)
        assert second_lock is not None
        assert second_lock.modules["fake-mod"].commit == second_sha
        assert seen == ["main", "main"]

    def test_unresolved_when_resolver_fails(
        self, app: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail(url: str, ref: str) -> str:
            raise ResolutionError("offline")

        monkeypatch.setattr(operations._lock, "resolve_ref", _fail)

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        _write_fake_git_metadata(app)

        lock_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        m = lock.modules["fake-mod"]
        assert m.kind == "unresolved"
        assert m.commit is None

    def test_legacy_v1_lock_migrates_in_place(
        self, app: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An older nsx.lock on disk must not block ``nsx lock`` from regenerating."""

        fake_sha = "d" * 40
        monkeypatch.setattr(operations._lock, "resolve_ref", lambda url, ref: (fake_sha, "branch"))
        monkeypatch.setattr(
            operations._lock,
            "hash_git_artifact",
            lambda url, commit: "sha256:" + "e" * 64,
        )

        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        _write_fake_git_metadata(app)

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
        with pytest.raises(NSXLockError):
            read_lock(app)

        # `nsx lock` rewrites in place under the current schema.
        lock_app_impl(app)
        capsys.readouterr()

        lock = read_lock(app)
        assert lock is not None
        from neuralspotx.nsx_lock import LOCK_SCHEMA_VERSION

        assert lock.schema_version == LOCK_SCHEMA_VERSION
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
        monkeypatch.setattr(operations._lock, "resolve_ref", lambda url, ref: (sha, "branch"))
        monkeypatch.setattr(operations._lock, "resolve_commit", lambda url, ref: sha)
        monkeypatch.setattr(
            operations._lock,
            "hash_git_artifact",
            lambda url, commit: "sha256:" + "f" * 64,
        )
        _write_nsx_yml(
            app,
            [{"name": "fake-mod", "project": "fake-proj", "revision": "main"}],
            registry_overrides=_GIT_PROJECT_OVERRIDES,
        )
        _write_fake_git_metadata(app)
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
        monkeypatch.setattr(operations._lock, "resolve_commit", lambda url, ref: upstream)

        report = outdated_app_impl(app)

        payload = report.to_dict()
        assert report.outdated_count == 1
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

        report = outdated_app_impl(app)

        assert report.outdated_count == 0
        assert report.checked[0].status == "up-to-date"

    def test_non_git_kinds_are_skipped(
        self,
        app: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _make_vendored(app, "v1")
        _write_nsx_yml(app, [{"name": "v1", "source": {"vendored": True}}])
        lock_app_impl(app)
        capsys.readouterr()  # drain lock's stdout

        report = outdated_app_impl(app)

        assert report.outdated_count == 0
        assert report.checked == ()


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
        if "nsx-board-apollo510-evb" in reg.get("modules", {}):
            return "nsx-board-apollo510-evb"
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

    def test_sync_repairs_mutated_packaged_tree(self, app: Path) -> None:
        """Sync must re-copy a packaged module from the wheel resource.

        Regression: previously ``_vendor_packaged_module_into_app``
        resolved its source via ``_module_metadata_path(...,
        app_dir=app_dir)``, which prefers an existing app-local
        vendored copy. If the user mutated that copy, the resolver
        returned the mutated tree, the same-path no-op short-circuit
        kicked in, and sync became a no-op — leaving the tree drifted
        from the lock and producing a perpetual warning loop.
        """
        mod = self._pick_packaged_module()
        _write_nsx_yml(app, [{"name": mod}])

        lock_app_impl(app)
        sync_app_impl(app)

        lock = read_lock(app)
        assert lock is not None
        vendored_at = app / lock.modules[mod].vendored_at
        assert vendored_at.exists()

        # Drop a stomp file inside the vendored tree.
        stomp = vendored_at / "STOMP.txt"
        stomp.write_text("user-modified", encoding="utf-8")
        from neuralspotx.nsx_lock import hash_tree

        assert hash_tree(vendored_at) != lock.modules[mod].content_hash

        # Sync must re-copy from the wheel resource and remove STOMP.
        sync_app_impl(app, force=True)

        assert not stomp.exists(), "sync did not repair mutated packaged tree"
        assert hash_tree(vendored_at) == lock.modules[mod].content_hash

    def test_nsx_tooling_hash_stable_across_apps(self, tmp_path: Path) -> None:
        """``nsx-tooling`` content_hash must NOT depend on the app's module list.

        Regression for the ``lock-integrity`` CI failure: previously
        ``_write_app_module_file`` injected an app-specific
        ``modules.cmake`` into ``cmake/nsx/`` after ``_copy_packaged_tree``,
        and the post-sync verification re-hashed the destination tree
        including that overlay — producing a different "got" hash for
        every app's ``NSX_APP_MODULES`` list and a perpetual drift
        warning. The fix excludes auto-generated overlays from the
        packaged-module hash.
        """

        def lock_one(extra_vendored_modules: list[str]) -> str:
            modules = ["nsx-tooling", *extra_vendored_modules]
            d = tmp_path / f"app_{len(modules)}_{abs(hash(tuple(modules))) % 10000}"
            d.mkdir()
            for name in extra_vendored_modules:
                _make_vendored(d, name, content=name)
            _write_nsx_yml(
                d,
                [
                    {"name": "nsx-tooling"},
                    *[
                        {"name": name, "source": {"vendored": True}}
                        for name in extra_vendored_modules
                    ],
                ],
            )
            lock_app_impl(d)
            sync_app_impl(d)
            # `lock --check` must succeed (no drift).
            lock_app_impl(d, check=True)
            lk = read_lock(d)
            assert lk is not None
            return lk.modules["nsx-tooling"].content_hash

        h_a = lock_one([])
        h_b = lock_one(["app-extra-one"])
        h_c = lock_one(["app-extra-one", "app-extra-two"])
        assert h_a == h_b == h_c, (
            "nsx-tooling content_hash drifts with app's module list "
            f"(got {h_a!r}, {h_b!r}, {h_c!r})"
        )

    def test_nsx_tooling_frozen_sync_ignores_generated_modules_cmake(self, app: Path) -> None:
        _write_nsx_yml(app, [{"name": "nsx-tooling"}])

        lock_app_impl(app)
        sync_app_impl(app)

        assert (app / "cmake" / "nsx" / "modules.cmake").exists()
        sync_app_impl(app, frozen=True)


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

        cfg = yaml.safe_load((app / "nsx.yml").read_text(encoding="utf-8"))
        names = [m["name"] for m in cfg["modules"]]
        assert "my-aot" in names
        entry = next(m for m in cfg["modules"] if m["name"] == "my-aot")
        assert entry["source"]["vendored"] is True

    def test_gitignore_does_not_ignore_vendored_dir(self, app: Path) -> None:
        _write_nsx_yml(app)
        add_module_impl(app, "my-aot", vendored=True)

        gitignore = (app / "modules" / ".gitignore").read_text(encoding="utf-8")
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
        cfg = yaml.safe_load((app / "nsx.yml").read_text(encoding="utf-8"))
        assert cfg["modules"] in (None, [])
