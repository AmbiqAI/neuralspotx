"""Unit tests for the on-disk module artifact cache."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from neuralspotx import module_cache, module_registry

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestCachePathResolution:
    def test_root_honours_nsx_cache_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "nsx-cache"))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert module_cache.module_cache_root() == tmp_path / "nsx-cache" / "modules"

    def test_root_falls_back_to_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSX_CACHE_DIR", raising=False)
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
        assert module_cache.module_cache_root() == tmp_path / "xdg" / "nsx" / "modules"

    def test_entry_path_is_sharded_by_first_two_hex(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        digest = "abcd1234" + "0" * 56
        entry = module_cache.cache_entry_for_hash(f"sha256:{digest}")
        assert entry == tmp_path / "modules" / "ab" / digest[2:]

    def test_entry_path_accepts_raw_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        digest = "ff" + "1" * 62
        entry = module_cache.cache_entry_for_hash(digest)
        assert entry == tmp_path / "modules" / "ff" / digest[2:]

    @pytest.mark.parametrize(
        "bad",
        [
            "sha256:../../etc/passwd",
            "sha256:..",
            "sha256:abc/def",
            "sha256:",
            "",
            "sha256:zzzz",  # non-hex chars
        ],
    )
    def test_entry_path_rejects_non_hex_digest(
        self, bad: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        with pytest.raises(module_cache.InvalidContentHashError):
            module_cache.cache_entry_for_hash(bad)

    def test_lookup_returns_false_for_invalid_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)
        dest = tmp_path / "dest"
        # Crafted hash must NOT escape the cache root.
        assert module_cache.lookup("sha256:../../escape", dest) is False
        assert not dest.exists()

    def test_populate_is_noop_for_invalid_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)
        src = tmp_path / "src"
        _make_tree(src)
        # Must not write anywhere.
        module_cache.populate("sha256:../../escape", src)
        # Cache root should remain empty (no entries written).
        root = module_cache.module_cache_root()
        assert not root.exists() or not any(root.iterdir())


# ---------------------------------------------------------------------------
# Disable switch
# ---------------------------------------------------------------------------


class TestDisableSwitch:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "On"])
    def test_truthy_disables(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", value)
        assert module_cache.is_disabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
    def test_falsy_enabled(self, value: str, monkeypatch: pytest.MonkeyPatch) -> None:
        if value:
            monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", value)
        else:
            monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)
        assert module_cache.is_disabled() is False


# ---------------------------------------------------------------------------
# populate / lookup round-trip
# ---------------------------------------------------------------------------


def _make_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.txt").write_text("hello\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("world\n")


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)
    return tmp_path


class TestPopulateLookup:
    def test_populate_then_lookup_round_trip(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        digest = "sha256:" + "a" * 64

        module_cache.populate(digest, src)

        dest = cache_dir / "dest"
        assert module_cache.lookup(digest, dest) is True
        assert (dest / "a.txt").read_text() == "hello\n"
        assert (dest / "sub" / "b.txt").read_text() == "world\n"

    def test_lookup_miss_returns_false_and_leaves_dest_alone(self, cache_dir: Path) -> None:
        dest = cache_dir / "dest"
        dest.mkdir()
        (dest / "keep.txt").write_text("untouched")

        assert module_cache.lookup("sha256:" + "f" * 64, dest) is False
        assert (dest / "keep.txt").read_text() == "untouched"

    def test_lookup_replaces_existing_dest_on_hit(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        digest = "sha256:" + "b" * 64
        module_cache.populate(digest, src)

        dest = cache_dir / "dest"
        dest.mkdir()
        (dest / "stale.txt").write_text("old")

        assert module_cache.lookup(digest, dest) is True
        assert not (dest / "stale.txt").exists()
        assert (dest / "a.txt").exists()

    def test_disabled_skips_lookup_and_populate(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", "1")
        src = cache_dir / "src"
        _make_tree(src)
        digest = "sha256:" + "c" * 64

        module_cache.populate(digest, src)
        # Cache root never created
        assert not module_cache.module_cache_root().exists()

        dest = cache_dir / "dest"
        assert module_cache.lookup(digest, dest) is False

    def test_populate_is_idempotent(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        digest = "sha256:" + "d" * 64

        module_cache.populate(digest, src)
        # Mutate src; second populate should be a no-op (existing entry wins).
        (src / "a.txt").write_text("changed\n")
        module_cache.populate(digest, src)

        dest = cache_dir / "dest"
        assert module_cache.lookup(digest, dest) is True
        assert (dest / "a.txt").read_text() == "hello\n"

    def test_corrupt_cache_entry_is_treated_as_miss(self, cache_dir: Path) -> None:
        digest = "sha256:" + "e" * 64
        entry = module_cache.cache_entry_for_hash(digest)
        entry.parent.mkdir(parents=True, exist_ok=True)
        # Create a *file* where a directory is expected.
        entry.write_text("not a dir")

        dest = cache_dir / "dest"
        assert module_cache.lookup(digest, dest) is False


# ---------------------------------------------------------------------------
# Maintenance helpers
# ---------------------------------------------------------------------------


class TestMaintenance:
    def test_iter_entries_lists_populated_caches(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        for prefix in ("11", "22", "33"):
            module_cache.populate("sha256:" + prefix + "0" * 62, src)

        entries = module_cache.iter_entries()
        assert len(entries) == 3
        prefixes = sorted(e.parent.name for e in entries)
        assert prefixes == ["11", "22", "33"]

    def test_clear_removes_all_entries(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        for prefix in ("11", "22"):
            module_cache.populate("sha256:" + prefix + "0" * 62, src)

        removed = module_cache.clear()
        assert removed == 2
        assert module_cache.iter_entries() == []

    def test_clear_on_empty_root_returns_zero(self, cache_dir: Path) -> None:
        assert module_cache.clear() == 0


# ---------------------------------------------------------------------------
# Integration with _vendor_git_module_at_commit
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, Any] = {
    "projects": {
        "demo-proj": {
            "url": "https://example.com/demo.git",
            "revision": "main",
            "path": "modules/demo-proj",
        }
    },
    "modules": {
        "demo-mod": {
            "project": "demo-proj",
            "revision": "main",
            "metadata": "modules/demo-proj/nsx-module.yaml",
        }
    },
}


def _fake_clone(payload: dict[str, str]):
    """Return a callable that simulates ``git_clone_at_commit``.

    Counts invocations and writes a deterministic tree to ``dest``.
    """

    state = {"calls": 0}

    def _clone(url: str, dest: Path, commit: str) -> None:  # noqa: ARG001
        state["calls"] += 1
        Path(dest).mkdir(parents=True, exist_ok=True)
        for name, content in payload.items():
            (Path(dest) / name).write_text(content)
        # Simulate a .git that the caller is expected to strip.
        (Path(dest) / ".git").mkdir()
        (Path(dest) / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    return _clone, state


class TestVendorGitIntegration:
    def test_cache_miss_clones_and_populates(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        clone, state = _fake_clone({"file.txt": "v1"})
        monkeypatch.setattr(module_registry, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app1"
        app_dir.mkdir()
        digest = "sha256:" + "1" * 64
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 1
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text() == "v1"
        # .git must be stripped after vendor.
        assert not (clone_dir / ".git").exists()

        # Cache should now have an entry mirroring the stripped tree.
        entry = module_cache.cache_entry_for_hash(digest)
        assert entry.is_dir()
        assert (entry / "file.txt").read_text() == "v1"
        assert not (entry / ".git").exists()

    def test_cache_hit_skips_clone(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pre-populate the cache.
        src = cache_dir / "prebuilt"
        src.mkdir()
        (src / "file.txt").write_text("from-cache")
        digest = "sha256:" + "2" * 64
        module_cache.populate(digest, src)

        clone, state = _fake_clone({"file.txt": "should-not-appear"})
        monkeypatch.setattr(module_registry, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app2"
        app_dir.mkdir()
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 0
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text() == "from-cache"

    def test_no_content_hash_bypasses_cache(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        clone, state = _fake_clone({"file.txt": "v1"})
        monkeypatch.setattr(module_registry, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app3"
        app_dir.mkdir()
        # Calling without content_hash must still clone; cache untouched.
        module_registry._vendor_git_module_at_commit(app_dir, "demo-mod", _REGISTRY, "deadbeef")

        assert state["calls"] == 1
        assert not module_cache.module_cache_root().exists()

    def test_disabled_cache_falls_back_to_clone(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pre-populate (without disable), then disable: lookup must miss.
        src = cache_dir / "prebuilt"
        src.mkdir()
        (src / "file.txt").write_text("cached")
        digest = "sha256:" + "3" * 64
        module_cache.populate(digest, src)

        monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", "1")
        clone, state = _fake_clone({"file.txt": "fresh"})
        monkeypatch.setattr(module_registry, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app4"
        app_dir.mkdir()
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 1
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text() == "fresh"
