"""Canonical resolution of the nsx on-disk cache root.

Single source of truth for *where* nsx stores its per-user caches so the
module-artifact store (:mod:`neuralspotx.module_cache`), the git-artifact
hash cache (:mod:`neuralspotx.nsx_lock`) and the resolve-ref cache
(:mod:`neuralspotx._resolve_cache`) all agree on one root.

Resolution precedence:

- ``NSX_CACHE_DIR`` — explicit override; used verbatim (expanded).
- else ``$XDG_CACHE_HOME/nsx`` if ``XDG_CACHE_HOME`` is set.
- else ``~/.cache/nsx``.

This module is a stdlib-only leaf with no intra-package imports so every
cache layer can depend on it without risking an import cycle.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["nsx_cache_root"]


def nsx_cache_root() -> Path:
    """Return the base nsx cache directory (parent of the per-cache files).

    Honours ``NSX_CACHE_DIR`` if set, else falls back to
    ``$XDG_CACHE_HOME/nsx`` or ``~/.cache/nsx``.
    """

    override = os.environ.get("NSX_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "nsx"
