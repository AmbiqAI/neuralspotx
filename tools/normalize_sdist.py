#!/usr/bin/env python3
"""Normalize a Python sdist tarball for reproducible publication."""

from __future__ import annotations

import argparse
import gzip
import io
import os
import tarfile
import tempfile
from pathlib import Path


def normalize_sdist(path: Path, *, epoch: int) -> None:
    """Rewrite *path* with stable gzip and tar metadata."""

    members: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, mode="r:gz") as source:
        for original in source.getmembers():
            payload = None
            if original.isfile():
                extracted = source.extractfile(original)
                if extracted is None:
                    raise ValueError(f"Could not read sdist member: {original.name}")
                payload = extracted.read()
            member = tarfile.TarInfo(original.name)
            member.type = original.type
            member.mode = original.mode
            member.size = original.size
            member.linkname = original.linkname
            member.devmajor = original.devmajor
            member.devminor = original.devminor
            member.mtime = epoch
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {
                key: value
                for key, value in original.pax_headers.items()
                if key not in {"mtime", "atime", "ctime"} and not key.startswith("SCHILY.")
            }
            members.append((member, payload))

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw,
                compresslevel=9,
                mtime=epoch,
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as target:
                    for member, payload in sorted(members, key=lambda item: item[0].name):
                        target.addfile(
                            member,
                            io.BytesIO(payload) if payload is not None else None,
                        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sdist", type=Path)
    parser.add_argument("--epoch", type=int, required=True)
    args = parser.parse_args()
    normalize_sdist(args.sdist, epoch=args.epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
