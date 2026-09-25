"""Git-aware hashing and vendoring for ``local_path`` projects."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXError
from neuralspotx.module_registry import _vendor_local_module_into_app
from neuralspotx.nsx_lock import hash_tree, read_lock
from neuralspotx.nsx_lock._git_files import git_ignores, git_listed_files
from neuralspotx.nsx_lock._hashing import hash_local_source
from neuralspotx.operations import lock_app_impl, sync_app_impl
from neuralspotx.project_config import _effective_registry, _load_registry

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_MODULE_YAML = "\n".join([
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=NSX Tests",
            "-c",
            "user.email=nsx-tests@example.invalid",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_project(root: Path) -> Path:
    """Committed project with an ignored build/."""

    _write(root / "nsx-module.yaml", _MODULE_YAML + "\n")
    _write(root / "src" / "kernel.c", "// v1\n")
    _write(root / "src" / "gone.c", "// deleted later\n")
    _write(root / ".gitignore", "build/\n*.log\n")
    _git(root, "init")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "init")
    return root


def _write_app(app: Path, source: Path) -> None:
    cfg: dict[str, Any] = {
        "schema_version": 2,
        "project": {"name": "testapp"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "baseline": "none",
        "modules": [{"name": "local-mod", "project": "local-proj", "revision": "main"}],
        "module_registry": {
            "projects": {
                "local-proj": {
                    "local_path": str(source),
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
    }
    app.mkdir(parents=True, exist_ok=True)
    _write(app / "nsx.yml", yaml.safe_dump(cfg, sort_keys=False))


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _lock_hash(app: Path) -> str:
    lock = read_lock(app)
    assert lock is not None
    return lock.modules["local-mod"].content_hash


class TestGitListedFiles:
    def test_lists_tracked_modified_untracked_not_ignored_or_deleted(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        _write(root / "src" / "kernel.c", "// modified\n")
        _write(root / "src" / "new.c", "// untracked\n")
        _write(root / "build" / "out.o", "ignored")
        _write(root / "run.log", "ignored")
        _write(root / ".venv" / "site.py", "excluded like hash_tree")
        (root / "src" / "gone.c").unlink()

        assert git_listed_files(root) == [
            ".gitignore",
            "nsx-module.yaml",
            "src/kernel.c",
            "src/new.c",
        ]

    def test_recurses_into_initialized_submodule(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        sub = root / "third_party" / "sub"
        _write(sub / "lib.c", "// sub tracked\n")
        _write(sub / ".gitignore", "artifacts/\n")
        _git(sub, "init")
        _git(sub, "add", ".")
        _git(sub, "commit", "-m", "sub")
        # Gitlink, as a submodule records it.
        _git(root, "add", "third_party/sub")
        _git(root, "commit", "-m", "add sub")
        _write(sub / "extra.c", "// sub untracked\n")
        _write(sub / "artifacts" / "big.bin", "ignored inside sub")

        listed = git_listed_files(root)
        assert listed is not None
        assert "third_party/sub/lib.c" in listed
        assert "third_party/sub/extra.c" in listed
        assert "third_party/sub/.gitignore" in listed
        assert not any("artifacts" in rel for rel in listed)
        assert "third_party/sub" not in listed

    def test_uninitialized_submodule_contributes_nothing(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        (root / "empty_sub").mkdir()
        _git(
            root,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{'1' * 40},empty_sub",
        )

        listed = git_listed_files(root)
        assert listed is not None
        assert not any(rel.startswith("empty_sub") for rel in listed)

    def test_non_git_and_subdirectory_return_none(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        _write(plain / "a.c", "x")
        root = _git_project(tmp_path / "proj")

        assert git_listed_files(plain) is None
        assert git_listed_files(root / "src") is None

    def test_ignores_git_location_env_from_hooks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _git_project(tmp_path / "proj")
        other = _git_project(tmp_path / "other")
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))

        assert git_listed_files(root) == [
            ".gitignore",
            "nsx-module.yaml",
            "src/gone.c",
            "src/kernel.c",
        ]


def _add_submodule(root: Path, rel: str) -> Path:
    """Committed nested repo recorded as a gitlink."""

    sub = root / rel
    _write(sub / "lib.c", "// sub tracked\n")
    _write(sub / ".gitignore", "build/\n")
    _git(sub, "init")
    _git(sub, "add", ".")
    _git(sub, "commit", "-m", "sub")
    _git(root, "add", rel)
    _git(root, "commit", "-m", "add sub")
    return sub


def test_git_ignores_follows_nearest_repo(tmp_path: Path) -> None:
    root = _git_project(tmp_path / "proj")
    sub = _add_submodule(root, "Tests/tester")
    (sub / "build").mkdir()

    assert git_ignores(root / "build" / "app" / "modules" / "x")
    assert not git_ignores(root / "apps" / "app" / "modules" / "x")
    assert git_ignores(sub / "build" / "app" / "modules" / "x")
    assert not git_ignores(sub / "app" / "modules" / "x")


class TestHashLocalSource:
    def test_ignored_changes_keep_hash(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        before = hash_local_source(root)

        _write(root / "build" / "out.o", "artifact v1")
        _write(root / "run.log", "log")
        assert hash_local_source(root) == before
        _write(root / "build" / "out.o", "artifact v2")
        assert hash_local_source(root) == before

    def test_listed_changes_move_hash_and_revert_restores(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        before = hash_local_source(root)

        _write(root / "src" / "kernel.c", "// edit\n")
        assert hash_local_source(root) != before
        _write(root / "src" / "kernel.c", "// v1\n")
        assert hash_local_source(root) == before

        _write(root / "src" / "new.c", "// untracked\n")
        assert hash_local_source(root) != before

    def test_non_git_matches_hash_tree(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        _write(plain / "a.c", "x")
        _write(plain / "build" / "out.o", "kept without git")
        _write(plain / ".gitignore", "build/\n")
        _write(plain / "__pycache__" / "m.pyc", "excluded")

        assert hash_local_source(plain) == hash_tree(plain)
        assert hash_local_source(tmp_path / "missing") == hash_tree(tmp_path / "missing")

    def test_git_hash_equals_hash_of_listed_copy(self, tmp_path: Path) -> None:
        root = _git_project(tmp_path / "proj")
        _write(root / "build" / "out.o", "ignored")
        # "a-b" sorts before "a/" as text.
        _write(root / "a" / "x.c", "1")
        _write(root / "a-b" / "x.c", "2")
        copy = tmp_path / "copy"
        for rel in git_listed_files(root) or []:
            _write(copy / rel, (root / rel).read_text(encoding="utf-8"))

        assert hash_local_source(root) == hash_tree(copy)


class TestLockAndSync:
    def test_vendors_only_listed_files_and_prunes(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        _write(source / "build" / "out.o", "ignored")
        _write(source / "src" / "new.c", "// untracked\n")
        app = tmp_path / "app"
        _write_app(app, source)

        lock_app_impl(app)
        sync_app_impl(app)
        vendored = app / "modules" / "local-proj"
        assert _files(vendored) == {
            ".gitignore",
            "nsx-module.yaml",
            "src/gone.c",
            "src/kernel.c",
            "src/new.c",
        }
        sync_app_impl(app, frozen=True)

        (source / "src" / "gone.c").unlink()
        _write(vendored / "stray.txt", "not listed")
        lock_app_impl(app)
        sync_app_impl(app, force=True)
        assert _files(vendored) == {".gitignore", "nsx-module.yaml", "src/kernel.c", "src/new.c"}
        sync_app_impl(app, frozen=True)

    def test_read_only_file_survives_revendor(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        generated = source / "src" / "gen.h"
        _write(generated, "// generated\n")
        generated.chmod(0o444)
        app = tmp_path / "app"
        _write_app(app, source)
        lock_app_impl(app)
        sync_app_impl(app)

        _write(source / "src" / "kernel.c", "// edit\n")
        lock_app_impl(app)
        sync_app_impl(app, frozen=True)
        vendored = app / "modules" / "local-proj" / "src" / "kernel.c"
        assert vendored.read_text(encoding="utf-8") == "// edit\n"

    @pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges")
    def test_directory_symlink_is_kept_as_link(self, tmp_path: Path) -> None:
        source = tmp_path / "proj"
        _write(source / "real" / "r.h", "// real\n")
        (source / "inc").mkdir(parents=True)
        (source / "inc" / "alias").symlink_to("../real")
        source = _git_project(source)
        app = tmp_path / "app"
        _write_app(app, source)
        lock_app_impl(app)
        sync_app_impl(app)

        alias = app / "modules" / "local-proj" / "inc" / "alias"
        assert alias.is_symlink()
        assert (alias / "r.h").read_text(encoding="utf-8") == "// real\n"
        sync_app_impl(app, frozen=True)

    def test_ignored_churn_keeps_frozen_sync_green(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        app = tmp_path / "app"
        _write_app(app, source)
        lock_app_impl(app)
        sync_app_impl(app)
        recorded = _lock_hash(app)

        _write(source / "build" / "artifact.bin", os.urandom(64).hex())
        sync_app_impl(app, frozen=True)
        lock_app_impl(app)
        assert _lock_hash(app) == recorded

    def test_edit_drifts_then_revert_restores(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        app = tmp_path / "app"
        _write_app(app, source)
        lock_app_impl(app)
        sync_app_impl(app)
        recorded = _lock_hash(app)

        _write(source / "src" / "kernel.c", "// edit\n")
        with pytest.raises(NSXError):
            sync_app_impl(app, frozen=True)
        _write(source / "src" / "kernel.c", "// v1\n")
        sync_app_impl(app, frozen=True)
        assert _lock_hash(app) == recorded

    def test_non_git_source_vendors_every_file(self, tmp_path: Path) -> None:
        source = tmp_path / "plain"
        _write(source / "nsx-module.yaml", _MODULE_YAML + "\n")
        _write(source / "build" / "out.o", "kept without git")
        _write(source / ".gitignore", "build/\n")
        _write(source / ".venv" / "site.py", "excluded")
        app = tmp_path / "app"
        _write_app(app, source)

        lock_app_impl(app)
        sync_app_impl(app)
        assert _lock_hash(app) == hash_tree(source)
        assert _files(app / "modules" / "local-proj") == {
            ".gitignore",
            "build/out.o",
            "nsx-module.yaml",
        }
        sync_app_impl(app, frozen=True)


class TestDestinationInsideSource:
    def test_gitignored_destination_vendors(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        app = source / "build" / "app"
        _write_app(app, source)

        lock_app_impl(app)
        sync_app_impl(app)
        vendored = app / "modules" / "local-proj"
        assert _files(vendored) == {".gitignore", "nsx-module.yaml", "src/gone.c", "src/kernel.c"}
        # The copy stays out of the hash.
        sync_app_impl(app, frozen=True)
        recorded = _lock_hash(app)
        lock_app_impl(app)
        assert _lock_hash(app) == recorded

    @pytest.mark.parametrize("use_git", [True, False])
    def test_listed_destination_is_refused(self, tmp_path: Path, use_git: bool) -> None:
        source = _git_project(tmp_path / "proj") if use_git else tmp_path / "proj"
        _write(source / "nsx-module.yaml", _MODULE_YAML + "\n")
        app = source / "apps" / "app"
        _write_app(app, source)
        nsx_cfg = yaml.safe_load((app / "nsx.yml").read_text(encoding="utf-8"))
        registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app)

        _vendor_local_module_into_app(app, "local-mod", registry)
        assert not (app / "modules" / "local-proj").exists()

    def test_app_ignoring_its_own_modules_is_refused(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        app = source / "apps" / "app"
        _write_app(app, source)
        # NSX's own modules/.gitignore must not count.
        _write(app / "modules" / ".gitignore", "local-proj/\n")
        (app / "modules" / "local-proj").mkdir()
        nsx_cfg = yaml.safe_load((app / "nsx.yml").read_text(encoding="utf-8"))
        registry = _effective_registry(_load_registry(), nsx_cfg, app_dir=app)

        _vendor_local_module_into_app(app, "local-mod", registry)
        assert not any((app / "modules" / "local-proj").iterdir())

    def test_gitignored_destination_inside_submodule_vendors(self, tmp_path: Path) -> None:
        source = _git_project(tmp_path / "proj")
        sub = _add_submodule(source, "Tests/tester")
        app = sub / "build" / "app"
        _write_app(app, source)

        lock_app_impl(app)
        sync_app_impl(app)
        vendored = app / "modules" / "local-proj"
        assert "Tests/tester/lib.c" in _files(vendored)
        assert not any(rel.startswith("Tests/tester/build") for rel in _files(vendored))
        sync_app_impl(app, frozen=True)
