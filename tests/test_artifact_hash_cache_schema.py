"""Git-artifact-hash cache schema and semantic versioning.

The versioned artifact-hash cache under ``$NSX_CACHE_DIR`` records a
``schema_version`` key. This test pins:

  * Writes always include ``schema_version`` and an ``entries`` map.
  * Legacy and v1 records are invalidated because they predate recursive
    submodule hydration.
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
    hash_git_artifact,
    hash_tree,
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

    def test_round_trip_current_schema(self, cache_dir: Path) -> None:
        original = {"u@c1": "sha256:1", "u@c2": "sha256:2"}
        _write_artifact_hash_cache(original)
        loaded = _read_artifact_hash_cache()
        assert loaded == original

    def test_legacy_flat_layout_is_invalidated(self, cache_dir: Path) -> None:
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"u@c1": "sha256:legacy"}),
            encoding="utf-8",
        )
        assert _read_artifact_hash_cache() == {}

    def test_v1_layout_is_invalidated(self, cache_dir: Path) -> None:
        path = _git_artifact_hash_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "schema_version": 1,
                "entries": {"u@c1": "sha256:stale-pre-submodule-hash"},
            }),
            encoding="utf-8",
        )
        assert _read_artifact_hash_cache() == {}

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

    def test_stale_v1_entry_is_recomputed_and_migrated(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx import subprocess_utils

        url = "https://example.com/repo.git"
        commit = "a" * 40
        legacy_path = cache_dir / "git-artifact-hashes.json"
        legacy_path.write_text(
            json.dumps({
                "schema_version": 1,
                "entries": {f"{url}@{commit}": "sha256:stale"},
            }),
            encoding="utf-8",
        )
        calls = 0

        def fake_clone(_url: str, dest: Path, _commit: str) -> None:
            nonlocal calls
            calls += 1
            nested = dest / "submodule"
            nested.mkdir(parents=True)
            (nested / "hydrated.txt").write_text("recursive content\n", encoding="utf-8")

        monkeypatch.setattr(subprocess_utils, "git_clone_at_commit", fake_clone)
        expected_tree = cache_dir / "expected"
        fake_clone(url, expected_tree, commit)
        calls = 0
        expected = hash_tree(expected_tree)

        assert hash_git_artifact(url, commit) == expected
        assert calls == 1
        path = _git_artifact_hash_cache_path()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == {
            "schema_version": _ARTIFACT_HASH_CACHE_SCHEMA_VERSION,
            "entries": {f"{url}@{commit}": expected},
        }
        assert json.loads(legacy_path.read_text(encoding="utf-8"))["schema_version"] == 1

    def test_recursive_submodule_files_affect_git_artifact_hash(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx import subprocess_utils

        def fake_clone(_url: str, dest: Path, _commit: str) -> None:
            nested = dest / "external" / "nested-submodule"
            nested.mkdir(parents=True)
            (dest / "root.txt").write_text("root\n", encoding="utf-8")
            (nested / "payload.txt").write_text("hydrated\n", encoding="utf-8")
            (dest / ".git").mkdir()
            (nested / ".git").write_text("gitdir: metadata\n", encoding="utf-8")

        monkeypatch.setattr(subprocess_utils, "git_clone_at_commit", fake_clone)
        actual = hash_git_artifact("https://example.com/repo.git", "b" * 40, use_cache=False)

        expected_tree = cache_dir / "expected-recursive"
        fake_clone("", expected_tree, "")
        (expected_tree / ".git").rmdir()
        (expected_tree / "external" / "nested-submodule" / ".git").unlink()
        assert actual == hash_tree(expected_tree)


def test_kws_locks_use_recursive_ns_cmsis_nn_hash() -> None:
    lock_text = (
        Path(__file__).parents[1] / "examples" / "kws_infer" / "nsx.lock"
    ).read_text(encoding="utf-8")
    old_hash = "sha256:9e99a00415678aaed59dde525eb51fc4f0e8f978139d72a876f93db38e238368"
    new_hash = "sha256:f5977cb5a973a139c23c4348c1c0dd9aa9edb659b15ec876197010a6b3f81311"

    assert old_hash not in lock_text
    assert lock_text.count(new_hash) == 3
