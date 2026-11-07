"""Targeted updates tested against independently controlled remote state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import api, operations
from neuralspotx._errors import NSXConfigError, NSXError
from neuralspotx.nsx_lock import LockKind, ResolutionError, read_lock, write_lock
from neuralspotx.operations import lock_app_impl


@dataclass
class App:
    root: Path
    config: dict[str, Any]
    remote: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    hashes: list[tuple[str, str]] = field(default_factory=list)

    def save(self) -> None:
        (self.root / "nsx.yml").write_text(yaml.safe_dump(self.config, sort_keys=False))

    def add(
        self, name: str, project: str | None = None, ref: str = "main", *, direct: bool = True
    ) -> None:
        project = project or name
        registry = self.config["module_registry"]
        url = f"https://example.invalid/{project}.git"
        registry["projects"].setdefault(project, {"url": url, "path": f"modules/{project}"})
        registry["modules"][name] = {
            "project": project,
            "revision": ref,
            "metadata": f"{name}/nsx-module.yaml",
        }
        metadata = self.root / "modules" / project / name / "nsx-module.yaml"
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(
            yaml.safe_dump({
                "schema_version": 1,
                "module": {"name": name, "type": "runtime", "version": "1.0.0"},
                "support": {"ambiqsuite": True, "zephyr": False},
                "build": {
                    "cmake": {"package": name.replace("-", "_"), "targets": [f"nsx::{name}"]}
                },
                "depends": {"required": [], "optional": []},
                "compatibility": {
                    "boards": ["*"],
                    "socs": ["*"],
                    "toolchains": ["arm-none-eabi-gcc"],
                },
            })
        )
        (metadata.parent / "CMakeLists.txt").write_text("")
        if direct:
            self.config["modules"].append({"name": name})
        self.remote.setdefault((url, ref), ("a" * 40, "tag" if ref.startswith("v") else "branch"))
        self.save()

    def advance(self) -> None:
        self.remote = {key: ("b" * 40, value[1]) for key, value in self.remote.items()}
        self.calls.clear()
        self.hashes.clear()

    def resolve(self, url: str, ref: str) -> tuple[str, str]:
        self.calls.append((url, ref))
        if len(ref) == 40:
            return ref, "commit"
        try:
            return self.remote[url, ref]
        except KeyError as exc:
            raise ResolutionError("fixture remote unavailable") from exc

    def artifact(self, url: str, commit: str) -> str:
        self.hashes.append((url, commit))
        return "sha256:" + commit[0] * 64


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    result = App(
        tmp_path,
        {
            "schema_version": 2,
            "project": {"name": "targeted"},
            "baseline": "none",
            "target": {"board": "apollo510_evb", "soc": "apollo510"},
            "toolchain": "arm-none-eabi-gcc",
            "modules": [],
            "module_registry": {"projects": {}, "modules": {}},
        },
    )
    monkeypatch.setattr(operations._lock, "resolve_ref", result.resolve)
    monkeypatch.setattr(operations._lock, "hash_git_artifact", result.artifact)
    # No real cache invalidation or accidental network acquisition in this fixture.
    monkeypatch.setattr("neuralspotx._resolve_cache.invalidate_all", lambda: None)
    monkeypatch.setattr(
        "neuralspotx.module_registry._vendoring._ensure_module_cloned", lambda *_: None
    )
    return result


@pytest.mark.parametrize("ref", ["main", "deadbee", "v1", "c" * 40])
def test_project_selection_preserves_unrelated_and_hashes_old_commit(app: App, ref: str) -> None:
    app.add("one", "shared", ref)
    app.add("two", "shared", ref)
    app.add("other", ref=ref)
    old = lock_app_impl(app.root)
    app.advance()
    new = api.lock_app(app.root, update=True, modules=["one"])
    expected = "c" * 40 if len(ref) == 40 else "b" * 40
    assert new.modules["one"].commit == new.modules["two"].commit == expected
    assert new.modules["other"].commit == old.modules["other"].commit
    assert app.calls == [("https://example.invalid/shared.git", ref)]
    assert ("https://example.invalid/other.git", old.modules["other"].commit) in app.hashes


def test_distinct_projects_with_same_url_are_not_selected_together(app: App) -> None:
    app.add("one")
    app.add("other")
    app.config["module_registry"]["projects"]["other"]["url"] = "https://example.invalid/one.git"
    app.save()
    lock_app_impl(app.root)
    app.advance()
    result = lock_app_impl(app.root, update=True, modules=["one"])
    assert result.modules["one"].commit == "b" * 40
    assert result.modules["other"].commit == "a" * 40


@pytest.mark.parametrize("change", ["url", "project", "constraint", "unresolved"])
def test_incompatible_unselected_entries_resolve(app: App, change: str) -> None:
    app.add("one")
    app.add("other")
    old = lock_app_impl(app.root)
    registry = app.config["module_registry"]
    if change == "url":
        registry["projects"]["other"]["url"] = "https://example.invalid/new.git"
        app.remote["https://example.invalid/new.git", "main"] = ("a" * 40, "branch")
    elif change == "project":
        registry["projects"]["new"] = registry["projects"]["other"].copy()
        registry["modules"]["other"]["project"] = "new"
    elif change == "constraint":
        registry["modules"]["other"]["revision"] = "next"
        app.remote["https://example.invalid/other.git", "next"] = ("a" * 40, "branch")
    else:
        old.modules["other"].kind = LockKind.UNRESOLVED
        old.modules["other"].commit = None
        write_lock(app.root, old, "apollo510_evb")
    app.save()
    app.advance()
    result = lock_app_impl(app.root, update=True, modules=["one"])
    assert result.modules["other"].commit == "b" * 40


def test_new_and_removed_dependencies_follow_materialized_metadata(app: App) -> None:
    app.add("one")
    app.add("old", direct=False)
    app.add("new", direct=False)
    metadata = app.root / "modules/one/one/nsx-module.yaml"
    data = yaml.safe_load(metadata.read_text())
    data["depends"]["required"] = ["old"]
    metadata.write_text(yaml.safe_dump(data))
    lock_app_impl(app.root)
    app.advance()
    data["depends"]["required"] = ["new"]
    metadata.write_text(yaml.safe_dump(data))
    result = lock_app_impl(app.root, update=True, modules=["one"])
    assert set(result.modules) == {"one", "new"}
    assert result.modules["new"].commit == "b" * 40


@pytest.mark.parametrize("first", ["one", "two"])
@pytest.mark.parametrize("failure", ["different-commits", "unresolved"])
def test_conflicting_shared_directory_does_not_write_lock(
    app: App, first: str, failure: str
) -> None:
    app.add(first, "shared", "main" if first == "one" else "next")
    app.add("two" if first == "one" else "one", "shared", "next" if first == "one" else "main")
    lock_app_impl(app.root)
    before = (app.root / "nsx.lock").read_bytes()
    app.advance()
    if failure == "unresolved":
        del app.remote["https://example.invalid/shared.git", "next"]
    else:
        app.remote["https://example.invalid/shared.git", "next"] = ("c" * 40, "branch")
    with pytest.raises(NSXConfigError, match="one.*two.*shared project directory"):
        lock_app_impl(app.root, update=True, modules=["one"])
    assert (app.root / "nsx.lock").read_bytes() == before


def test_check_applies_selection_without_writing(app: App) -> None:
    app.add("one")
    app.add("other")
    lock_app_impl(app.root)
    before = {p.relative_to(app.root): p.read_bytes() for p in app.root.rglob("*") if p.is_file()}
    app.advance()
    # Only unrelated upstream moves: targeted check succeeds.
    app.remote["https://example.invalid/one.git", "main"] = ("a" * 40, "branch")
    api.lock_app(app.root, update=True, modules=["one"], check=True)
    assert app.calls == [("https://example.invalid/one.git", "main")]
    app.remote["https://example.invalid/one.git", "main"] = ("b" * 40, "branch")
    with pytest.raises(NSXError):
        api.lock_app(app.root, update=True, modules=["one"], check=True)
    after = {p.relative_to(app.root): p.read_bytes() for p in app.root.rglob("*") if p.is_file()}
    assert before == after


def test_missing_lock_and_api_selection_without_update(app: App) -> None:
    app.add("one")
    app.add("other")
    result = api.lock_app(app.root, update=True, modules=["one"])
    assert len(result.modules) == 2
    app.advance()
    result = api.lock_app(app.root, modules=["one"])
    assert result.modules["other"].commit == "b" * 40


def test_targets_validate_names_globally_before_writes(app: App) -> None:
    app.add("one")
    app.add("other")
    del app.config["target"]
    app.config["targets"] = {
        "default": "apollo510_evb",
        "supported": ["apollo510_evb", "apollo510b_evb"],
    }
    app.config["modules"][0]["boards"] = ["apollo510b_evb"]
    app.save()
    lock_app_impl(app.root)
    before = (app.root / "nsx.lock").read_bytes()
    app.advance()
    with pytest.raises(NSXConfigError, match="absent.*missing"):
        lock_app_impl(app.root, update=True, modules=["one", "missing"])
    assert (app.root / "nsx.lock").read_bytes() == before
    lock_app_impl(app.root, update=True, modules=["one"])
    first, second = read_lock(app.root, "apollo510_evb"), read_lock(app.root, "apollo510b_evb")
    assert first is not None and second is not None
    assert "one" not in first.modules
    assert second.modules["one"].commit == "b" * 40
    assert first.modules["other"].commit == second.modules["other"].commit == "a" * 40
    with pytest.raises(NSXConfigError, match="absent"):
        lock_app_impl(app.root, update=True, modules=["one"], board="apollo510_evb")
    lock_app_impl(app.root, update=True, modules=["other"], board="apollo510_evb")
    unchanged = read_lock(app.root, "apollo510b_evb")
    assert unchanged is not None and unchanged.modules == second.modules


def test_non_git_selection_does_not_select_synthetic_project_name(app: App) -> None:
    app.add("gitmod", "localmod")
    app.config["modules"].append({"name": "localmod", "source": {"vendored": True}})
    # Vendored module's synthetic project name collides with gitmod's project.
    app.save()
    lock_app_impl(app.root)
    app.advance()
    result = lock_app_impl(app.root, update=True, modules=["localmod"])
    assert result.modules["gitmod"].commit == "a" * 40
    assert app.calls == []


def test_selected_same_commit_hash_failure_reuses_prior_hash(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.add("one")
    old = lock_app_impl(app.root)

    def unavailable(*_args: str) -> str:
        raise OSError("fixture artifact unavailable")

    monkeypatch.setattr(operations._lock, "hash_git_artifact", unavailable)
    new = lock_app_impl(app.root, update=True, modules=["one"])
    assert new.modules["one"].content_hash == old.modules["one"].content_hash


def test_shared_project_update_then_frozen_sync_from_local_git(
    app: App, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Real Git commits and tree hashes, with no remote service or fake sync."""
    import shutil
    import subprocess

    from neuralspotx.nsx_lock import hash_git_artifact, resolve_ref
    from neuralspotx.operations import sync_app_impl

    app.add("one", "shared")
    app.add("two", "shared")
    upstream = tmp_path / "upstream"
    shutil.copytree(app.root / "modules/shared", upstream)

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(upstream), *args], text=True).strip()

    git("init", "-b", "main")
    git("config", "user.name", "NSX test")
    git("config", "user.email", "nsx-test@example.invalid")
    git("add", ".")
    git("commit", "-m", "initial artifact")
    old_commit = git("rev-parse", "HEAD")
    # Production rejects file transports. Admit only this fixture's repository
    # at the transport boundary so real resolve/hash/sync run without a server.
    from neuralspotx.subprocess_utils import _git

    def allow_fixture_url(url: str) -> None:
        assert url == upstream.as_uri()

    monkeypatch.setattr(_git, "_validate_git_url", allow_fixture_url)
    monkeypatch.setattr(_git, "GIT_PROTOCOL_ALLOWLIST_FLAGS", ("-c", "protocol.file.allow=always"))
    app.config["module_registry"]["projects"]["shared"]["url"] = upstream.as_uri()
    app.save()
    monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("NSX_RESOLVE_TTL", "0")
    monkeypatch.setattr(operations._lock, "resolve_ref", resolve_ref)
    monkeypatch.setattr(operations._lock, "hash_git_artifact", hash_git_artifact)
    original = lock_app_impl(app.root)
    assert original.modules["one"].commit == old_commit
    (upstream / "payload.txt").write_text("updated artifact\n")
    git("add", ".")
    git("commit", "-m", "new artifact")
    new_commit = git("rev-parse", "HEAD")
    updated = lock_app_impl(app.root, update=True, modules=["one"])
    assert updated.modules["one"].commit == updated.modules["two"].commit == new_commit
    assert updated.modules["one"].content_hash != original.modules["one"].content_hash
    sync_app_impl(app.root)
    assert (app.root / "modules/shared/payload.txt").read_text() == "updated artifact\n"
    sync_app_impl(app.root, frozen=True)


def test_unresolved_only_shared_directory_uses_content_identity(app: App) -> None:
    import shutil

    app.add("one")
    app.add("two")
    # Two offline sources describe one local fallback artifact.
    shutil.copytree(app.root / "modules/two/two", app.root / "modules/one/two")
    app.config["module_registry"]["projects"]["two"]["path"] = "modules/one"
    app.save()
    app.remote.clear()
    old = lock_app_impl(app.root)
    result = lock_app_impl(app.root, update=True, modules=["one"])
    assert {row.kind for row in result.modules.values()} == {LockKind.UNRESOLVED}
    assert result.modules["one"].url != result.modules["two"].url
    assert result.modules["one"].content_hash == result.modules["two"].content_hash
    assert result.modules["one"].content_hash == old.modules["one"].content_hash


def test_unresolved_only_conflicting_hashes_are_rejected(tmp_path: Path) -> None:
    from neuralspotx.nsx_lock import NsxLock, ResolvedModule
    from neuralspotx.operations._lock_selection import validate_materialization

    lock = NsxLock(
        modules={
            name: ResolvedModule(
                project=name,
                kind=LockKind.UNRESOLVED,
                constraint="main",
                vendored_at="modules/shared",
                content_hash="sha256:" + char * 64,
                acquired_at="",
                url=f"https://example.invalid/{name}.git",
            )
            for name, char in (("one", "a"), ("two", "b"))
        }
    )
    with pytest.raises(NSXConfigError, match="resolved artifacts differ"):
        validate_materialization(tmp_path, lock)
