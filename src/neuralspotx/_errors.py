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


class NSXError(SystemExit, RuntimeError):
    """Raised when an NSX workflow operation fails.

    Inherits from both :class:`SystemExit` and :class:`RuntimeError` so
    the same exception object satisfies legacy ``except SystemExit:``
    handlers (the CLI top-level wrapper, pre-existing tests,
    ``pipx``/``argparse`` semantics) **and** new typed handlers
    (``except NSXError:``, ``except NSXLockError:``).  Library internals
    can migrate from ``raise SystemExit(msg)`` to
    ``raise NSX*Error(msg)`` site-by-site without breaking either
    consumer.
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
    """Raised when the per-app advisory lock cannot be acquired."""


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
