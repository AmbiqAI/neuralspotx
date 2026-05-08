"""Regression tests for the "Next" remediation items in REVIEW.md.

Covers:
1. Cache concurrency hardening for the resolve-ref cache and the
   git-artifact-hash cache (sidecar ``file_mutex``).
2. Operation-scope module-metadata memoization
   (``module_registry.metadata_cache_scope``).
3. ``LockKind`` enum is str-compatible with the existing
   ``ResolvedModule.kind: str`` field.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from neuralspotx import _resolve_cache, module_registry, nsx_lock
from neuralspotx.file_lock import file_mutex

# ---------------------------------------------------------------------------
# 1. Cache concurrency: resolve-ref cache
# ---------------------------------------------------------------------------


class TestResolveCacheConcurrency:
    def test_concurrent_puts_do_not_lose_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("NSX_RESOLVE_TTL", "3600")

        n_threads = 8
        per_thread = 25
        barrier = threading.Barrier(n_threads)

        def worker(idx: int) -> None:
            barrier.wait()
            for j in range(per_thread):
                _resolve_cache.put(
                    f"https://example.com/repo-{idx}.git",
                    f"ref-{j}",
                    sha=f"{idx:02d}{j:02d}" + "a" * 36,
                    kind="branch",
                )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every (url, ref) pair we wrote must round-trip; nothing dropped.
        for i in range(n_threads):
            for j in range(per_thread):
                got = _resolve_cache.get(f"https://example.com/repo-{i}.git", f"ref-{j}")
                assert got is not None, f"missing entry ({i},{j})"
                sha, kind = got
                assert sha == f"{i:02d}{j:02d}" + "a" * 36
                assert kind == "branch"


# ---------------------------------------------------------------------------
# 1b. Cache concurrency: artifact-hash cache
# ---------------------------------------------------------------------------


class TestArtifactHashCacheConcurrency:
    def test_concurrent_writes_do_not_lose_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the same RMW pattern that ``hash_git_artifact`` uses, but
        without invoking the (subprocess-heavy) clone path. We exercise
        the cache file directly under the same sidecar mutex so the
        observable concurrency contract — no lost updates — is pinned.
        """

        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))

        cache_path = nsx_lock._git_artifact_hash_cache_path()
        lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")

        n_threads = 8
        per_thread = 25
        barrier = threading.Barrier(n_threads)

        def worker(idx: int) -> None:
            barrier.wait()
            for j in range(per_thread):
                key = f"https://example.com/repo-{idx}.git@" + f"{idx:02d}{j:02d}" + "f" * 36
                value = f"sha256:{idx:02d}{j:02d}" + "0" * 60
                with file_mutex(lock_path):
                    cache = nsx_lock._read_artifact_hash_cache()
                    cache[key] = value
                    nsx_lock._write_artifact_hash_cache(cache)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        cache = nsx_lock._read_artifact_hash_cache()
        assert len(cache) == n_threads * per_thread


# ---------------------------------------------------------------------------
# 2. Operation-scope metadata cache
# ---------------------------------------------------------------------------


class TestMetadataCacheScope:
    def _stub_loader(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
        """Replace the disk-touching helpers in ``_load_module_metadata``
        with deterministic in-memory fakes, and return a hit-counter
        keyed by module name. Lets us prove the contextvar cache really
        elides repeat calls.
        """

        calls: dict[str, int] = {}

        def fake_entry_for(_registry: dict[str, Any], name: str) -> Any:
            class _Entry:
                project = name
                revision = "main"
                metadata = f"modules/{name}/nsx-module.yaml"

            return _Entry()

        def fake_path(
            module_name: str,
            _entry: Any,
            _registry: dict[str, Any],
            *,
            app_dir: Path | None,
        ) -> Path:
            return Path(f"/fake/{module_name}/nsx-module.yaml")

        def fake_read(path: Path) -> dict[str, Any]:
            name = path.parent.name
            calls[name] = calls.get(name, 0) + 1
            return {
                "module": {"name": name, "type": "runtime", "version": "0.1.0"},
                "support": {"ambiqsuite": True},
                "build": {"cmake": {"targets": [name]}},
                "depends": {"required": [], "optional": []},
                "compatibility": {
                    "boards": ["apollo510_evb"],
                    "socs": ["apollo510"],
                    "toolchains": ["gcc"],
                },
            }

        def fake_validate(_data: dict[str, Any], _path: str) -> None:
            return None

        monkeypatch.setattr(module_registry, "registry_entry_for_module", fake_entry_for)
        monkeypatch.setattr(module_registry, "_module_metadata_path", fake_path)
        monkeypatch.setattr(module_registry, "_read_yaml", fake_read)
        monkeypatch.setattr(module_registry, "validate_nsx_module_metadata", fake_validate)
        return calls

    def test_repeated_loads_inside_scope_hit_cache_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._stub_loader(monkeypatch)
        registry: dict[str, Any] = {"modules": {}, "projects": {}}

        with module_registry.metadata_cache_scope():
            for _ in range(5):
                module_registry._load_module_metadata("ns-foo", registry)
                module_registry._load_module_metadata("ns-bar", registry)

        assert calls == {"ns-foo": 1, "ns-bar": 1}

    def test_no_caching_outside_scope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._stub_loader(monkeypatch)
        registry: dict[str, Any] = {"modules": {}, "projects": {}}

        for _ in range(3):
            module_registry._load_module_metadata("ns-foo", registry)

        assert calls == {"ns-foo": 3}

    def test_scope_isolation_between_concurrent_callers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two threads each open their own scope — neither should see
        the other's cached entries (``ContextVar`` is task-local).
        """

        calls = self._stub_loader(monkeypatch)
        registry: dict[str, Any] = {"modules": {}, "projects": {}}
        barrier = threading.Barrier(2)

        def worker(_idx: int) -> None:
            with module_registry.metadata_cache_scope():
                module_registry._load_module_metadata("ns-foo", registry)
                barrier.wait()
                module_registry._load_module_metadata("ns-foo", registry)

        ta = threading.Thread(target=worker, args=(0,))
        tb = threading.Thread(target=worker, args=(1,))
        ta.start()
        tb.start()
        ta.join()
        tb.join()
        # Each thread loads once (scope-local cache) — total 2 disk reads.
        assert calls == {"ns-foo": 2}


# ---------------------------------------------------------------------------
# 3. LockKind enum is string-compatible
# ---------------------------------------------------------------------------


class TestLockKindEnum:
    def test_enum_compares_equal_to_string(self) -> None:
        assert nsx_lock.LockKind.GIT == "git"
        assert nsx_lock.LockKind.PACKAGED == "packaged"
        assert nsx_lock.LockKind.LOCAL == "local"
        assert nsx_lock.LockKind.VENDORED == "vendored"
        assert nsx_lock.LockKind.UNRESOLVED == "unresolved"

    def test_resolved_module_str_kind_round_trips_through_yaml(self) -> None:
        m = nsx_lock.ResolvedModule(
            project="x",
            kind="git",
            constraint="main",
            vendored_at="modules/x",
            content_hash="sha256:" + "a" * 64,
            acquired_at="2026-01-01T00:00:00+00:00",
            url="https://example.com/x.git",
            commit="b" * 40,
        )
        out = m.to_yaml_dict()
        # Serialised value must remain a plain string for YAML safety.
        assert out["kind"] == "git"
        assert isinstance(out["kind"], str)
        assert type(out["kind"]).__name__ == "str"

    def test_lock_kinds_set_lists_all_members(self) -> None:
        assert nsx_lock.LOCK_KINDS == {
            "git",
            "packaged",
            "local",
            "vendored",
            "unresolved",
        }
