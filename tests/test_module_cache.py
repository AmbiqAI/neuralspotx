"""Unit tests for the on-disk module artifact cache."""

from __future__ import annotations

import threading
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
    (root / "a.txt").write_text("hello\n", encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("world\n", encoding="utf-8")


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
        assert (dest / "a.txt").read_text(encoding="utf-8") == "hello\n"
        assert (dest / "sub" / "b.txt").read_text(encoding="utf-8") == "world\n"

    def test_lookup_miss_returns_false_and_leaves_dest_alone(self, cache_dir: Path) -> None:
        dest = cache_dir / "dest"
        dest.mkdir()
        (dest / "keep.txt").write_text("untouched", encoding="utf-8")

        assert module_cache.lookup("sha256:" + "f" * 64, dest) is False
        assert (dest / "keep.txt").read_text(encoding="utf-8") == "untouched"

    def test_lookup_replaces_existing_dest_on_hit(self, cache_dir: Path) -> None:
        src = cache_dir / "src"
        _make_tree(src)
        digest = "sha256:" + "b" * 64
        module_cache.populate(digest, src)

        dest = cache_dir / "dest"
        dest.mkdir()
        (dest / "stale.txt").write_text("old", encoding="utf-8")

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
        (src / "a.txt").write_text("changed\n", encoding="utf-8")
        module_cache.populate(digest, src)

        dest = cache_dir / "dest"
        assert module_cache.lookup(digest, dest) is True
        assert (dest / "a.txt").read_text(encoding="utf-8") == "hello\n"

    def test_corrupt_cache_entry_is_treated_as_miss(self, cache_dir: Path) -> None:
        digest = "sha256:" + "e" * 64
        entry = module_cache.cache_entry_for_hash(digest)
        entry.parent.mkdir(parents=True, exist_ok=True)
        # Create a *file* where a directory is expected.
        entry.write_text("not a dir", encoding="utf-8")

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
            (Path(dest) / name).write_text(content, encoding="utf-8")
        # Simulate a .git that the caller is expected to strip.
        (Path(dest) / ".git").mkdir()
        (Path(dest) / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    return _clone, state


class TestVendorGitIntegration:
    def test_registry_commit_revision_uses_detached_checkout(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        commit = "a" * 40
        registry = {
            "projects": {
                "demo-proj": {
                    "url": "https://example.com/demo.git",
                    "revision": commit,
                    "path": "modules/demo-proj",
                }
            },
            "modules": {
                "demo-mod": {
                    "project": "demo-proj",
                    "revision": commit,
                    "metadata": "modules/demo-proj/nsx-module.yaml",
                }
            },
        }
        calls: list[tuple[str, Path, str]] = []

        def fake_clone_at_commit(url: str, dest: Path, rev: str) -> None:
            calls.append((url, dest, rev))
            dest.mkdir(parents=True)
            (dest / "file.txt").write_text("ok", encoding="utf-8")
            (dest / ".git").mkdir()

        def fail_branch_clone(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("raw commit revision must not use git clone --branch")

        monkeypatch.setattr(module_registry._vendoring, "git_clone", fail_branch_clone)
        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", fake_clone_at_commit)

        app_dir = cache_dir / "app0"
        app_dir.mkdir()
        module_registry._ensure_module_cloned(app_dir, "demo-mod", registry)

        assert calls == [
            ("https://example.com/demo.git", app_dir / "modules" / "demo-proj", commit)
        ]
        assert (app_dir / "modules" / "demo-proj" / "file.txt").exists()
        assert not (app_dir / "modules" / "demo-proj" / ".git").exists()

    def test_cache_miss_clones_and_populates(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        clone, state = _fake_clone({"file.txt": "v1"})
        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app1"
        app_dir.mkdir()
        digest = "sha256:" + "1" * 64
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 1
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text(encoding="utf-8") == "v1"
        # .git must be stripped after vendor.
        assert not (clone_dir / ".git").exists()

        # Cache should now have an entry mirroring the stripped tree.
        entry = module_cache.cache_entry_for_hash(digest)
        assert entry.is_dir()
        assert (entry / "file.txt").read_text(encoding="utf-8") == "v1"
        assert not (entry / ".git").exists()

    def test_vendor_strips_nested_submodule_git_metadata(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_clone(_url: str, dest: Path, _commit: str) -> None:
            nested = dest / "external" / "submodule"
            nested.mkdir(parents=True)
            (dest / ".git").mkdir()
            (nested / ".git").write_text("gitdir: ../../.git/modules/submodule\n")

        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", fake_clone)

        app_dir = cache_dir / "nested-git"
        app_dir.mkdir()
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef"
        )

        clone_dir = app_dir / "modules" / "demo-proj"
        assert not (clone_dir / ".git").exists()
        assert not (clone_dir / "external" / "submodule" / ".git").exists()

    def test_cache_hit_skips_clone(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pre-populate the cache.
        src = cache_dir / "prebuilt"
        src.mkdir()
        (src / "file.txt").write_text("from-cache", encoding="utf-8")
        digest = "sha256:" + "2" * 64
        module_cache.populate(digest, src)

        clone, state = _fake_clone({"file.txt": "should-not-appear"})
        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app2"
        app_dir.mkdir()
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 0
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text(encoding="utf-8") == "from-cache"

    def test_no_content_hash_bypasses_cache(
        self,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        clone, state = _fake_clone({"file.txt": "v1"})
        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", clone)

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
        (src / "file.txt").write_text("cached", encoding="utf-8")
        digest = "sha256:" + "3" * 64
        module_cache.populate(digest, src)

        monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", "1")
        clone, state = _fake_clone({"file.txt": "fresh"})
        monkeypatch.setattr(module_registry._vendoring, "git_clone_at_commit", clone)

        app_dir = cache_dir / "app4"
        app_dir.mkdir()
        module_registry._vendor_git_module_at_commit(
            app_dir, "demo-mod", _REGISTRY, "deadbeef", content_hash=digest
        )

        assert state["calls"] == 1
        clone_dir = app_dir / "modules" / "demo-proj"
        assert (clone_dir / "file.txt").read_text(encoding="utf-8") == "fresh"


# ---------------------------------------------------------------------------
# R19: Concurrency tests
# ---------------------------------------------------------------------------

_VALID_HASH_PREFIX = "sha256:"


def _make_source_tree(root: Path, name: str, content: str = "hello") -> Path:
    """Create a simple source tree for cache population."""
    src = root / name
    src.mkdir(parents=True, exist_ok=True)
    (src / "file.txt").write_text(content, encoding="utf-8")
    (src / "sub").mkdir(exist_ok=True)
    (src / "sub" / "nested.txt").write_text(f"nested-{name}", encoding="utf-8")
    return src


class TestModuleCacheConcurrencyR19:
    def test_concurrent_populate_same_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple threads populating the same digest must produce one valid entry."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)

        digest = _VALID_HASH_PREFIX + "aa" + "1" * 62
        n_threads = 8
        barrier = threading.Barrier(n_threads)
        errors: list[str] = []

        def worker(idx: int) -> None:
            src = _make_source_tree(tmp_path / "sources", f"src-{idx}")
            barrier.wait()
            try:
                module_cache.populate(digest, src)
            except Exception as exc:
                errors.append(f"worker {idx}: {exc}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"populate errors: {errors}"

        # The cache entry must exist and be a valid directory
        entry = module_cache.cache_entry_for_hash(digest)
        assert entry.is_dir()
        assert (entry / "file.txt").exists()

        # lookup must succeed
        dest = tmp_path / "dest"
        assert module_cache.lookup(digest, dest) is True
        assert (dest / "file.txt").exists()

        # No leftover temp directories
        shard = entry.parent
        leftovers = [p for p in shard.iterdir() if ".tmp." in p.name]
        assert not leftovers, f"temp dirs left behind: {leftovers}"

    def test_concurrent_populate_different_digests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent populates for different digests must not interfere."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)

        n_threads = 6
        barrier = threading.Barrier(n_threads)
        digests = [_VALID_HASH_PREFIX + f"{i:02d}" + "2" * 62 for i in range(n_threads)]
        errors: list[str] = []

        def worker(idx: int) -> None:
            src = _make_source_tree(tmp_path / "sources", f"mod-{idx}", content=f"content-{idx}")
            barrier.wait()
            try:
                module_cache.populate(digests[idx], src)
            except Exception as exc:
                errors.append(f"worker {idx}: {exc}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        # Every digest should be independently cached
        for i, digest in enumerate(digests):
            dest = tmp_path / f"lookup-{i}"
            assert module_cache.lookup(digest, dest) is True
            assert (dest / "file.txt").read_text(encoding="utf-8") == f"content-{i}"

    def test_concurrent_lookup_during_populate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """lookup() racing with populate() must return False or a complete tree."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.delenv("NSX_DISABLE_MODULE_CACHE", raising=False)

        digest = _VALID_HASH_PREFIX + "bb" + "3" * 62
        n_lookups = 6
        iterations = 20
        barrier = threading.Barrier(1 + n_lookups)
        errors: list[str] = []

        def populator() -> None:
            barrier.wait()
            for i in range(iterations):
                src = _make_source_tree(tmp_path / "pop-sources", f"iter-{i}", content=f"v{i}")
                module_cache.populate(digest, src)

        def looker(idx: int) -> None:
            barrier.wait()
            for i in range(iterations):
                dest = tmp_path / f"look-{idx}-{i}"
                try:
                    hit = module_cache.lookup(digest, dest)
                    if hit:
                        # Must be a complete tree
                        if not (dest / "file.txt").exists():
                            errors.append(f"looker {idx} iter {i}: hit but missing file.txt")
                        if not (dest / "sub" / "nested.txt").exists():
                            errors.append(f"looker {idx} iter {i}: hit but missing nested.txt")
                except Exception as exc:
                    errors.append(f"looker {idx} iter {i}: {exc}")

        threads = [threading.Thread(target=populator)]
        threads += [threading.Thread(target=looker, args=(i,)) for i in range(n_lookups)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"lookup errors during populate: {errors}"


# ---------------------------------------------------------------------------
# Public api.cache_info / api.clean_cache wrappers
# ---------------------------------------------------------------------------


class TestPublicCacheApi:
    def test_cache_info_returns_typed_snapshot(self, cache_dir: Path) -> None:
        from neuralspotx import api
        from neuralspotx.models import CacheInfo

        src = cache_dir / "src"
        _make_tree(src)
        for prefix in ("aa", "bb"):
            module_cache.populate("sha256:" + prefix + "0" * 62, src)

        info = api.cache_info()
        assert isinstance(info, CacheInfo)
        assert info.disabled is False
        assert info.entry_count == 2
        assert info.total_size_bytes > 0
        digests = sorted(e.digest for e in info.entries)
        assert digests == [
            "aa" + "0" * 62,
            "bb" + "0" * 62,
        ]
        # to_dict matches CacheInfo's own properties
        d = info.to_dict()
        assert d["entry_count"] == 2
        assert d["total_size_bytes"] == info.total_size_bytes

    def test_clean_cache_dry_run_preserves_entries(self, cache_dir: Path) -> None:
        from neuralspotx import api
        from neuralspotx.models import CacheCleanResult

        src = cache_dir / "src"
        _make_tree(src)
        module_cache.populate("sha256:" + "cc" + "0" * 62, src)

        result = api.clean_cache(dry_run=True)
        assert isinstance(result, CacheCleanResult)
        assert result.dry_run is True
        assert result.removed_count == 1
        # Nothing was actually removed.
        assert len(module_cache.iter_entries()) == 1

    def test_clean_cache_removes_entries(self, cache_dir: Path) -> None:
        from neuralspotx import api

        src = cache_dir / "src"
        _make_tree(src)
        for prefix in ("dd", "ee", "ff"):
            module_cache.populate("sha256:" + prefix + "0" * 62, src)

        result = api.clean_cache()
        assert result.dry_run is False
        assert result.removed_count == 3
        assert module_cache.iter_entries() == []

    def test_cache_info_reflects_disabled_env(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx import api

        monkeypatch.setenv("NSX_DISABLE_MODULE_CACHE", "1")
        info = api.cache_info()
        assert info.disabled is True
