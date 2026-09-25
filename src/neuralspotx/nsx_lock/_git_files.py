"""Git file listing for ``local_path`` projects."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path, PurePosixPath

from .._logging import get_logger
from ._constants import _HASH_EXCLUDE_DIRS

_log = get_logger(__name__)

# Repo-location vars a git hook may set.
_GIT_LOCATION_ENV = frozenset({
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_WORK_TREE",
})


def _git_output(root: Path, *args: str) -> bytes | None:
    """Run git in root; None on failure."""

    env = {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_ENV}
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            env=env,
            check=False,
        )
    except OSError:
        return None
    return done.stdout if done.returncode == 0 else None


def git_listed_files(root: Path) -> list[str] | None:
    """Unignored files under a git top level, else None."""

    if not (root / ".git").exists():
        return None
    top = _git_output(root, "rev-parse", "--show-toplevel")
    if top is not None and Path(os.fsdecode(top).strip()).resolve() != root.resolve():
        return None
    listing = None
    if top is not None:
        listing = _git_output(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if listing is None:
        _log.warning("git could not list %s; using every file.", root)
        return None

    files: list[str] = []
    # Nested repos list as "dir/".
    for rel in sorted({name.rstrip("/") for name in os.fsdecode(listing).split("\0") if name}):
        if any(part in _HASH_EXCLUDE_DIRS for part in PurePosixPath(rel).parts):
            continue
        path = root / rel
        if path.is_dir() and not path.is_symlink():
            # Submodule: list it the same way.
            files.extend(f"{rel}/{sub}" for sub in git_listed_files(path) or ())
        elif path.is_file() or path.is_symlink():
            files.append(rel)
    return files


def git_ignores(path: Path) -> bool:
    """Whether git ignores a path, existing or not."""

    base = path.parent
    while not base.is_dir():
        base = base.parent
    rel = path.relative_to(base).as_posix()
    return _git_output(base, "check-ignore", "-q", rel) is not None
