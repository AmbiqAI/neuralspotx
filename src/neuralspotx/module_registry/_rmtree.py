"""Cross-version ``shutil.rmtree`` wrapper that tolerates read-only files."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def _rmtree(path: Path) -> None:
    """Remove a directory tree, handling read-only files on Windows.

    Git pack-index files are marked read-only; ``shutil.rmtree`` fails
    on Windows unless we clear the read-only flag first.
    """

    def _on_rm_error(_func, _path, _exc_info):  # noqa: ANN001
        try:
            os.chmod(_path, stat.S_IWRITE)
        except OSError:
            pass
        try:
            os.unlink(_path)
        except (OSError, TypeError):
            pass

    # ``onerror=`` is deprecated in 3.12 and removed in 3.14. The
    # callback ignores the third arg's shape so it works for both APIs.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=_on_rm_error)
