"""Phase 3 — `git-artifact-hashes.json` cache schema versioning (#64).

The artifact-hash cache (``$NSX_CACHE_DIR/git-artifact-hashes.json``)
gained a ``schema_version`` key in nsx 0.10. This test pins:

  * Writes always include ``schema_version`` and an ``entries`` map.
  * Legacy flat-mapping cache files (no ``schema_version`` key) still
    load as v1 so user caches survive the upgrade.
  * A future cache with ``schema_version`` higher than this nsx
    supports raises :class:`NSXCacheError` with an actionable
    remediation message.
  * The reader accepts a v1 file (round-trip).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from neuralspotx import NSXCacheError
from neuralspotx.nsx_lock import (
    _ARTIFACT_HASH_CACHE_SCHEMA_VERSION,
    _git_artifact_hash_cache_path,
    _read_artifact_hash_cache,
    _write_artifact_hash_cache,
)


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("NSX_CACHE_DIR", str(tmp_path))
    return tmp_path


class TestArtifactHashCacheSchema:
    def test_writer_includes_schema_version_header(self, cache_dir: Path) -> None:
        _write_artifact_hash_cache({"https://example/repo.git@abc": "sha256:deadbeef"})
        path = _git_artifact_hash_cache_path()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["schema_version"] == _ARTIFACT_HASH_CACHE_SCHEMA_VERSION
        assert on_disk["entries"] == {"https://example/repo.git@abc": "sha256:deadbeef"}

    def test_round_trip_v1(self, cache_dir: Path) -> None:
        original = {"u@c1": "sha256:1", "u@c2": "sha256:2"}
        _write_artifact_hash_cache(original)
        loaded = _read_artifact_hash_cache()
        assert loaded == original

    def test_legacy_flat_layout_is_accepted(self, cache_dir: Path) -> None:
        # nsx releases before this change wrote the cache as a flat
        # ``{key: hash}`` JSON object with no header. Those files must
        # continue to load so user caches don't have to be discarded.
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"u@c1": "sha256:legacy"}),
            encoding="utf-8",
        )
        loaded = _read_artifact_hash_cache()
        assert loaded == {"u@c1": "sha256:legacy"}

    def test_future_schema_raises_nsx_cache_error(self, cache_dir: Path) -> None:
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "schema_version": _ARTIFACT_HASH_CACHE_SCHEMA_VERSION + 1,
                "entries": {"u@c1": "sha256:future"},
            }),
            encoding="utf-8",
        )
        with pytest.raises(NSXCacheError, match="schema_version"):
            _read_artifact_hash_cache()

    def test_corrupt_header_returns_empty(self, cache_dir: Path) -> None:
        # A corrupt or unparseable header is treated as if the cache
        # were absent so the next writer can overwrite cleanly.
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": "not-an-int", "entries": {}}),
            encoding="utf-8",
        )
        assert _read_artifact_hash_cache() == {}

    def test_missing_file_returns_empty(self, cache_dir: Path) -> None:
        path = _git_artifact_hash_cache_path()
        if path.exists():
            os.unlink(path)
        assert _read_artifact_hash_cache() == {}

    def test_writer_overwrites_legacy_layout_with_versioned_layout(self, cache_dir: Path) -> None:
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"u@c1": "sha256:legacy"}),
            encoding="utf-8",
        )
        _write_artifact_hash_cache({"u@c1": "sha256:legacy", "u@c2": "sha256:new"})
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["schema_version"] == _ARTIFACT_HASH_CACHE_SCHEMA_VERSION
        assert on_disk["entries"] == {
            "u@c1": "sha256:legacy",
            "u@c2": "sha256:new",
        }
