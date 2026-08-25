from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import tarfile
import urllib.error
from email.message import Message
from pathlib import Path
from types import TracebackType

import pytest

ROOT = Path(__file__).parents[1]


def _load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


normalize_sdist = _load_tool("normalize_sdist").normalize_sdist
reconcile = _load_tool("reconcile_pypi_artifacts").reconcile


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sdist(path: Path, *, mtime: int, uid: int, uname: str) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="source.tar", mode="wb", fileobj=raw, mtime=mtime) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, payload in (("demo-1.0/", None), ("demo-1.0/data.txt", b"data\n")):
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.DIRTYPE if payload is None else tarfile.REGTYPE
                    member.mode = 0o755 if payload is None else 0o644
                    member.mtime = mtime
                    member.uid = uid
                    member.gid = uid
                    member.uname = uname
                    member.gname = "group"
                    member.size = len(payload or b"")
                    archive.addfile(member, io.BytesIO(payload) if payload else None)


def test_normalize_sdist_removes_time_and_owner_drift(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, mtime=100, uid=501, uname="first")
    _write_sdist(second, mtime=200, uid=502, uname="second")

    normalize_sdist(first, epoch=42)
    normalize_sdist(second, epoch=42)

    assert _sha(first) == _sha(second)
    with tarfile.open(first) as archive:
        for member in archive.getmembers():
            assert member.mtime == 42
            assert member.uid == member.gid == 0
            assert member.uname == member.gname == ""


def test_build_backend_is_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"setuptools==83.0.0"' in pyproject
    assert '"wheel==0.47.0"' in pyproject
    assert '"packaging==26.3"' in pyproject


def test_reconcile_restores_hash_verified_canonical_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "demo-1.0-py3-none-any.whl"
    artifact.write_bytes(b"rebuilt")
    canonical = tmp_path / "canonical.whl"
    canonical.write_bytes(b"canonical")
    expected = _sha(canonical)
    response = {
        "urls": [
            {
                "filename": artifact.name,
                "digests": {"sha256": expected},
                "url": canonical.as_uri(),
            }
        ]
    }

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            return None

    def urlopen(url, timeout):
        if str(url).startswith("https://pypi.org/"):
            return Response(json.dumps(response).encode())
        assert str(url) == canonical.as_uri()
        return Response(canonical.read_bytes())

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    records = reconcile(dist, project="demo", version="1.0")

    assert artifact.read_bytes() == b"canonical"
    assert records[0]["rebuilt_sha256"] != records[0]["canonical_sha256"]
    assert records[0]["action"] == "restored-canonical-pypi-bytes"


def test_reconcile_rejects_missing_canonical_artifact(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "demo-1.0-py3-none-any.whl").write_bytes(b"wheel")
    response = {
        "urls": [
            {
                "filename": "demo-1.0-py3-none-any.whl",
                "digests": {"sha256": "0" * 64},
                "url": "https://example.invalid/wheel",
            },
            {
                "filename": "demo-1.0.tar.gz",
                "digests": {"sha256": "1" * 64},
                "url": "https://example.invalid/sdist",
            },
        ]
    }

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            return None

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _url, timeout: Response(json.dumps(response).encode()),
    )

    with pytest.raises(ValueError, match="filename sets differ"):
        reconcile(dist, project="demo", version="1.0")


def test_reconcile_allows_retry_before_pypi_publication(
    tmp_path: Path, monkeypatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "demo-1.0-py3-none-any.whl"
    artifact.write_bytes(b"deterministic-rebuild")

    def not_found(_url, timeout):
        raise urllib.error.HTTPError(
            "https://pypi.org/pypi/demo/1.0/json",
            404,
            "Not Found",
            Message(),
            None,
        )

    monkeypatch.setattr("urllib.request.urlopen", not_found)

    assert reconcile(dist, project="demo", version="1.0") == []
    assert artifact.read_bytes() == b"deterministic-rebuild"
