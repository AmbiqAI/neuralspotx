"""Tests for the persistent resolve-ref TTL cache."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from neuralspotx import _resolve_cache


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the cache at a temp directory and reset TTL to default."""
    monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("NSX_RESOLVE_TTL", raising=False)


class TestGetPut:
    def test_miss_on_empty_cache(self):
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_put_then_get(self):
        _resolve_cache.put("https://github.com/a/b", "main", "abc123" * 7, "branch")
        result = _resolve_cache.get("https://github.com/a/b", "main")
        assert result == ("abc123" * 7, "branch")

    def test_different_refs_are_separate(self):
        _resolve_cache.put("https://github.com/a/b", "main", "sha1" + "0" * 36, "branch")
        _resolve_cache.put("https://github.com/a/b", "v1.0", "sha2" + "0" * 36, "tag")
        assert _resolve_cache.get("https://github.com/a/b", "main") == (
            "sha1" + "0" * 36,
            "branch",
        )
        assert _resolve_cache.get("https://github.com/a/b", "v1.0") == (
            "sha2" + "0" * 36,
            "tag",
        )

    def test_kind_can_be_none(self):
        _resolve_cache.put("https://github.com/a/b", "HEAD", "abc" + "0" * 37, None)
        result = _resolve_cache.get("https://github.com/a/b", "HEAD")
        assert result == ("abc" + "0" * 37, None)


class TestTTL:
    def test_expired_entry_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NSX_RESOLVE_TTL", "1")
        _resolve_cache.put("https://github.com/a/b", "main", "a" * 40, "branch")
        # Patch time so the entry looks expired
        with patch.object(time, "time", return_value=time.time() + 10):
            assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_disabled_cache_ttl_zero(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NSX_RESOLVE_TTL", "0")
        _resolve_cache.put("https://github.com/a/b", "main", "a" * 40, "branch")
        # put is a no-op when disabled
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_custom_ttl_respected(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NSX_RESOLVE_TTL", "3600")
        _resolve_cache.put("https://github.com/a/b", "main", "b" * 40, "branch")
        # Even 10 min later it's still valid with 1h TTL
        with patch.object(time, "time", return_value=time.time() + 600):
            result = _resolve_cache.get("https://github.com/a/b", "main")
            assert result == ("b" * 40, "branch")


class TestInvalidateAll:
    def test_invalidate_removes_all_entries(self, tmp_path: Path):
        _resolve_cache.put("https://github.com/a/b", "main", "c" * 40, "branch")
        assert _resolve_cache.get("https://github.com/a/b", "main") is not None
        _resolve_cache.invalidate_all()
        assert _resolve_cache.get("https://github.com/a/b", "main") is None


class TestCorruptCache:
    def test_corrupt_json_returns_miss(self, tmp_path: Path):
        cache_file = tmp_path / "resolve-ref-cache.json"
        cache_file.write_text("not valid json {{{", encoding="utf-8")
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_wrong_schema_returns_miss(self, tmp_path: Path):
        cache_file = tmp_path / "resolve-ref-cache.json"
        cache_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_malformed_entry_returns_miss(self, tmp_path: Path):
        cache_file = tmp_path / "resolve-ref-cache.json"
        cache_file.write_text(
            json.dumps({"https://github.com/a/b\tmain": "not a list"}), encoding="utf-8"
        )
        assert _resolve_cache.get("https://github.com/a/b", "main") is None


class TestPruning:
    def test_stale_entries_pruned_on_put(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("NSX_RESOLVE_TTL", "10")
        cache_file = tmp_path / "resolve-ref-cache.json"
        # Seed a stale entry manually
        stale_ts = time.time() - 100
        data = {"https://github.com/old\told-ref": ["x" * 40, "branch", stale_ts]}
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        # Put a fresh entry — the stale one should be pruned
        _resolve_cache.put("https://github.com/new", "main", "y" * 40, "branch")

        raw = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "https://github.com/old\told-ref" not in raw
        assert "https://github.com/new\tmain" in raw


# ---------------------------------------------------------------------------
# R19: Concurrency tests
# ---------------------------------------------------------------------------


def _interprocess_put_worker(args: tuple[str, int, int]) -> None:
    """Worker for inter-process concurrent put() test."""
    cache_dir, idx, count = args
    import os

    os.environ["NSX_CACHE_DIR"] = cache_dir
    os.environ["NSX_RESOLVE_TTL"] = "3600"
    for j in range(count):
        _resolve_cache.put(
            f"https://example.com/repo-{idx}.git",
            f"ref-{j}",
            sha=f"{idx:02d}{j:02d}" + "a" * 36,
            kind="branch",
        )


class TestResolveCacheConcurrencyR19:
    def test_interprocess_concurrent_puts_preserve_all_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple processes writing distinct keys must not lose entries."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("NSX_RESOLVE_TTL", "3600")

        n_procs = 4
        per_proc = 20
        args = [(str(tmp_path), i, per_proc) for i in range(n_procs)]

        with multiprocessing.Pool(n_procs) as pool:
            pool.map(_interprocess_put_worker, args)

        for i in range(n_procs):
            for j in range(per_proc):
                got = _resolve_cache.get(f"https://example.com/repo-{i}.git", f"ref-{j}")
                assert got is not None, f"missing entry ({i},{j})"
                sha, kind = got
                assert sha == f"{i:02d}{j:02d}" + "a" * 36
                assert kind == "branch"

    def test_concurrent_reader_writer_no_malformed_reads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Readers must never see malformed data while writers are active."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("NSX_RESOLVE_TTL", "3600")

        n_writers = 4
        n_readers = 4
        iterations = 30
        errors: list[str] = []
        barrier = threading.Barrier(n_writers + n_readers)

        def writer(idx: int) -> None:
            barrier.wait()
            for j in range(iterations):
                _resolve_cache.put(
                    f"https://example.com/w-{idx}.git",
                    f"ref-{j}",
                    sha=f"{idx:02d}{j:02d}" + "b" * 36,
                    kind="tag",
                )

        def reader(idx: int) -> None:
            barrier.wait()
            for _ in range(iterations):
                # Read any key — the important thing is we never crash
                # or get partial/malformed data.
                try:
                    result = _resolve_cache.get(
                        f"https://example.com/w-{idx % n_writers}.git", "ref-0"
                    )
                    if result is not None:
                        sha, kind = result
                        if not isinstance(sha, str) or len(sha) != 40:
                            errors.append(f"bad sha: {sha!r}")
                        if kind not in ("tag", "branch", None):
                            errors.append(f"bad kind: {kind!r}")
                except Exception as exc:
                    errors.append(f"reader {idx} exception: {exc}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_writers)]
        threads += [threading.Thread(target=reader, args=(i,)) for i in range(n_readers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Reader observed bad data: {errors}"

    def test_invalidate_all_during_writes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invalidate_all() racing with put() must not corrupt the cache."""
        monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("NSX_RESOLVE_TTL", "3600")

        iterations = 40
        barrier = threading.Barrier(2)

        def writer() -> None:
            barrier.wait()
            for j in range(iterations):
                _resolve_cache.put(
                    "https://example.com/repo.git",
                    f"ref-{j}",
                    sha=f"{j:04d}" + "c" * 36,
                    kind="branch",
                )

        def invalidator() -> None:
            barrier.wait()
            for _ in range(iterations // 2):
                _resolve_cache.invalidate_all()

        t_w = threading.Thread(target=writer)
        t_i = threading.Thread(target=invalidator)
        t_w.start()
        t_i.start()
        t_w.join()
        t_i.join()

        # After the race, the cache file must be either absent or valid JSON.
        cache_file = tmp_path / "resolve-ref-cache.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
