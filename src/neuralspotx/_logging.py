"""Structured logging configuration for the ``neuralspotx`` package.

The CLI configures a single root logger (``neuralspotx``) at startup so
all diagnostic messages — warnings, progress notes, debug traces — flow
through one stream that callers can capture, redirect, or suppress.

Design split (REVIEW2 J1):

* **Logging (this module).** Diagnostics aimed at the operator: warnings,
  progress notes, debug detail. Routed to ``stderr`` so they never
  contaminate machine-readable command output.
* **`print()`.** Reserved for *command results* — the tables, JSON
  payloads, and "Created app at ..." confirmations that the user
  actually invoked ``nsx`` to produce. These remain on ``stdout``.

This split keeps `nsx outdated --json | jq` and similar pipelines clean
even at ``-vv`` while still letting embedders attach their own log
handlers via :func:`logging.getLogger("neuralspotx").addHandler`.
"""

from __future__ import annotations

import logging
import sys

ROOT_LOGGER_NAME = "neuralspotx"

# Module-level flag: did *we* (the CLI) attach our default handler? If
# so, ``configure_logging`` reconfigures it on subsequent calls (the
# common case is one call per ``main()`` invocation, but tests may
# reconfigure between cases). Embedders that attach their own handler
# before calling :func:`configure_logging` are not affected — we only
# adjust the level on our own handler.
_OUR_HANDLER: logging.Handler | None = None


def get_logger(name: str) -> logging.Logger:
    """Return a child of the ``neuralspotx`` root logger.

    Args:
        name: Usually ``__name__`` from the calling module. The leading
            ``neuralspotx.`` prefix is preserved so the logger sits under
            the package root.

    Returns:
        A ``logging.Logger`` whose effective level is inherited from the
        ``neuralspotx`` root logger (set by :func:`configure_logging`).
    """

    return logging.getLogger(name)


def _level_for(verbosity: int, *, quiet: bool) -> int:
    """Map CLI ``-v``/``-q`` counts onto a stdlib log level.

    Default (no flags) is ``WARNING`` so progress notes are silent but
    real warnings surface. ``-q`` raises the bar to ``ERROR``; each
    additional ``-v`` lowers it by one level.
    """

    if quiet:
        return logging.ERROR
    if verbosity <= 0:
        return logging.WARNING
    if verbosity == 1:
        return logging.INFO
    return logging.DEBUG  # -vv and beyond


def configure_logging(verbosity: int = 0, *, quiet: bool = False) -> None:
    """Configure the ``neuralspotx`` root logger from CLI flags.

    Idempotent: repeated calls reconfigure the handler we own without
    stacking duplicates. Embedders that attach their own handlers
    *before* calling this function keep them.

    Args:
        verbosity: Count of ``-v`` flags (0 = default, 1 = info,
            2+ = debug).
        quiet: When True, raises the threshold to ``ERROR`` regardless
            of *verbosity*. Mirrors ``-q``.
    """

    global _OUR_HANDLER

    level = _level_for(verbosity, quiet=quiet)
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level)

    if _OUR_HANDLER is None:
        handler = logging.StreamHandler(stream=sys.stderr)
        # Compact format: keep warnings short ("warning: foo") at default
        # verbosity so they read like the prior ``print("warning: ...")``
        # lines they replace; expand to ``LEVEL name: message`` at -vv so
        # debugging shows which module emitted what.
        handler.setFormatter(_CompactFormatter())
        root.addHandler(handler)
        # Do not propagate to the stdlib root logger — that would double
        # up output if a downstream embedder also configured ``logging``.
        root.propagate = False
        _OUR_HANDLER = handler

    _OUR_HANDLER.setLevel(level)


class _CompactFormatter(logging.Formatter):
    """Render WARNING as ``warning: msg`` and DEBUG as ``DEBUG name: msg``.

    This keeps the default user-visible output indistinguishable from
    the prior ``print("warning: ...")`` style, while ``-vv`` expands to
    a more diagnostic format that includes the logger name.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"error: {msg}"
        if record.levelno == logging.WARNING:
            return f"warning: {msg}"
        if record.levelno == logging.INFO:
            return f"note: {msg}"
        # DEBUG and below: include the logger name so the source is
        # obvious in -vv output.
        return f"debug {record.name}: {msg}"
