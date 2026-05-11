"""Lock-entry kind enum extracted from ``nsx_lock``."""

from __future__ import annotations

import enum


class LockKind(str, enum.Enum):
    """Resolution kind for a single lock entry.

    Mixed with ``str`` so existing code that compares ``entry.kind ==
    "git"`` keeps working unchanged. New code should prefer the enum
    members (``LockKind.GIT``) for static checking and refactor safety.
    """

    GIT = "git"
    PACKAGED = "packaged"
    LOCAL = "local"
    VENDORED = "vendored"
    UNRESOLVED = "unresolved"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


# Public, hashable set of valid kind strings, useful for parser
# validation without depending on the enum API.
LOCK_KINDS: frozenset[str] = frozenset(k.value for k in LockKind)
