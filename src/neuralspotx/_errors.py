"""NSX exception hierarchy.

Lives in its own module (no NSX imports) so internal layers
(``operations``, ``module_registry``, ``project_config``,
``subprocess_utils``, ``tooling``) can ``raise NSX*Error(...)`` directly
without pulling in :mod:`neuralspotx.api` and creating an import cycle.

The public surface is re-exported from :mod:`neuralspotx.api` and
:mod:`neuralspotx` so library consumers continue to write
``from neuralspotx import NSXError`` exactly as before.
"""

from __future__ import annotations


class NSXError(RuntimeError):
    """Raised when an NSX workflow operation fails.

    Library consumers catch typed errors via ``except NSXError:`` (or one
    of the more specific subclasses below).  The CLI wrapper translates
    these into a non-zero process exit code at the top level; embedders
    handle them as ordinary Python exceptions.
    """


class NSXTimeoutError(NSXError):
    """Raised when an NSX subprocess exceeded its ``timeout_s`` budget."""

    def __init__(
        self,
        message: str,
        *,
        command: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.timeout_s = timeout_s


class NSXConfigError(NSXError):
    """Raised for invalid or missing app / registry configuration."""


class NSXResolutionError(NSXError):
    """Raised for git-ref resolution or lock-file consistency failures."""


class NSXLockError(NSXError):
    """Raised for failures in the per-app advisory-lock subsystem.

    Covers both runtime acquisition failures (the platform lock
    primitive errors out, the lock is held by another process in
    non-blocking mode) and on-disk ``nsx.lock`` schema/format
    incompatibilities surfaced by readers like ``sync`` and
    ``outdated``.
    """


class NSXModuleError(NSXError):
    """Raised for module-name lookup or dependency-closure failures."""


class NSXToolchainError(NSXError):
    """Raised for missing or unsupported toolchain configuration."""


__all__ = [
    "NSXConfigError",
    "NSXError",
    "NSXLockError",
    "NSXModuleError",
    "NSXResolutionError",
    "NSXTimeoutError",
    "NSXToolchainError",
]
