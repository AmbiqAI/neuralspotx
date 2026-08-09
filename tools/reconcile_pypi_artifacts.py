#!/usr/bin/env python3
"""Reconcile rebuilt release artifacts with immutable files already on PyPI."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reconcile(dist: Path, *, project: str, version: str) -> list[dict[str, str]]:
    """Replace differing rebuilt files with hash-verified canonical PyPI files."""

    endpoint = f"https://pypi.org/pypi/{project}/{version}/json"
    try:
        with urllib.request.urlopen(endpoint, timeout=30) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise

    canonical = {
        entry["filename"]: entry
        for entry in release["urls"]
        if entry["filename"].endswith((".whl", ".tar.gz"))
    }
    local = {
        artifact.name
        for artifact in dist.iterdir()
        if artifact.is_file() and artifact.name.endswith((".whl", ".tar.gz"))
    }
    if local != set(canonical):
        raise ValueError(
            "Local/PyPI artifact filename sets differ: "
            f"local={sorted(local)}, pypi={sorted(canonical)}"
        )
    records: list[dict[str, str]] = []
    for artifact in sorted(dist.iterdir()):
        if not artifact.is_file() or artifact.name not in canonical:
            continue
        expected = canonical[artifact.name]["digests"]["sha256"]
        rebuilt = sha256(artifact)
        record = {
            "filename": artifact.name,
            "rebuilt_sha256": rebuilt,
            "canonical_sha256": expected,
            "source": canonical[artifact.name]["url"],
        }
        if rebuilt != expected:
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(dir=dist, delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    with urllib.request.urlopen(record["source"], timeout=60) as response:
                        while chunk := response.read(1024 * 1024):
                            temporary.write(chunk)
                if sha256(temporary_path) != expected:
                    raise ValueError(f"PyPI hash mismatch for {artifact.name}")
                temporary_path.replace(artifact)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            record["action"] = "restored-canonical-pypi-bytes"
        else:
            record["action"] = "rebuilt-bytes-match-pypi"
        records.append(record)

    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    records = reconcile(args.dist, project=args.project, version=args.version)
    args.report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pypi_release_exists": bool(records),
                "artifacts": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(args.report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
