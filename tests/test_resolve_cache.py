"""Tests for the persistent resolve-ref TTL cache."""

from __future__ import annotations

import json
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
        cache_file.write_text("not valid json {{{")
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_wrong_schema_returns_miss(self, tmp_path: Path):
        cache_file = tmp_path / "resolve-ref-cache.json"
        cache_file.write_text(json.dumps(["not", "a", "dict"]))
        assert _resolve_cache.get("https://github.com/a/b", "main") is None

    def test_malformed_entry_returns_miss(self, tmp_path: Path):
        cache_file = tmp_path / "resolve-ref-cache.json"
        cache_file.write_text(json.dumps({"https://github.com/a/b\tmain": "not a list"}))
        assert _resolve_cache.get("https://github.com/a/b", "main") is None


class TestPruning:
    def test_stale_entries_pruned_on_put(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("NSX_RESOLVE_TTL", "10")
        cache_file = tmp_path / "resolve-ref-cache.json"
        # Seed a stale entry manually
        stale_ts = time.time() - 100
        data = {"https://github.com/old\told-ref": ["x" * 40, "branch", stale_ts]}
        cache_file.write_text(json.dumps(data))

        # Put a fresh entry — the stale one should be pruned
        _resolve_cache.put("https://github.com/new", "main", "y" * 40, "branch")

        raw = json.loads(cache_file.read_text())
        assert "https://github.com/old\told-ref" not in raw
        assert "https://github.com/new\tmain" in raw
