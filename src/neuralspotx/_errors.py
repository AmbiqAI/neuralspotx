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
    """Raised for invalid or missing app / registry configuration.

    The optional ``field`` attribute names the offending YAML key path
    (dot-separated, with ``[i]`` for list indices, e.g.
    ``"modules[2].name"``) so structured callers can map an error back
    to a specific location in ``nsx.yml`` without re-parsing the
    message.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class NSXCacheError(NSXError):
    """Raised when an on-disk NSX cache file is unreadable or has an
    unsupported ``schema_version``.

    Catch alongside :class:`NSXError` for general failure handling, or
    specifically when offering remediation steps such as ``nsx cache
    clean``.
    """


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


class NSXIntegrityError(NSXModuleError):
    """Raised when a vendored module's content hash does not match
    the value recorded in ``nsx.lock``.

    Surfaced primarily by ``nsx sync --frozen`` when the on-disk tree
    has been mutated since the lock was written. Subclasses
    :class:`NSXModuleError` so existing ``except NSXModuleError`` sites
    continue to catch the failure.
    """

    def __init__(self, message: str, *, module: str | None = None) -> None:
        super().__init__(message)
        self.module = module


class NSXGitError(NSXError):
    """Raised for unsafe or rejected ``git`` operations.

    Used by ``git_clone_at_commit`` to refuse registry URLs that name
    disallowed transports such as ``ext::`` (arbitrary command
    execution) or ``file://`` / ``file::`` (local-filesystem
    redirection), which would otherwise bypass the registry's
    intended ``http(s)``/``ssh``/``git`` allow-list.
    """


class NSXToolchainError(NSXError):
    """Raised for missing or unsupported toolchain configuration."""


__all__ = [
    "NSXCacheError",
    "NSXConfigError",
    "NSXError",
    "NSXGitError",
    "NSXIntegrityError",
    "NSXLockError",
    "NSXModuleError",
    "NSXResolutionError",
    "NSXTimeoutError",
    "NSXToolchainError",
]
