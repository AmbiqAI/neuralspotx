"""Discovery-hint registry shared by every ``cmd_*`` handler.

Originally lived at the top of ``cli.py``. Promoted to a sibling module
so the handlers in ``_cmd_module.py`` / ``_cmd_cache.py`` can use the
``@command_hint`` decorator without importing ``cli/__init__.py`` (which
would create a circular import).
"""

from __future__ import annotations

from ..models import CommandCategory, CommandHint, CommandScope

# Discovery hints declared via the ``@command_hint(path, ...)`` decorator on each
# ``cmd_*`` handler. Group/root paths that have no dedicated handler
# (``""``, ``"module"``, ``"cache"``) are registered explicitly via
# :func:`_register_group_hint` from ``cli/__init__.py``.
_COMMAND_GRAPH_HINTS: dict[str, CommandHint] = {}


def command_hint(
    path: str,
    category: CommandCategory,
    scope: CommandScope,
    *next_commands: str,
    alias_for: str | None = None,
):
    """Register a :class:`CommandHint` for *path* and tag the handler.

    Keeps each command's discovery metadata co-located with its ``cmd_*``
    function instead of mirroring it in a far-away central table.
    """

    hint = CommandHint(category, scope, tuple(next_commands), alias_for=alias_for)

    def decorator(func):
        _COMMAND_GRAPH_HINTS[path] = hint
        func._nsx_hint = hint  # type: ignore[attr-defined]
        return func

    return decorator


def _register_group_hint(
    path: str,
    category: CommandCategory,
    scope: CommandScope,
    *next_commands: str,
) -> None:
    """Register a hint for a parser group (no leaf handler)."""

    _COMMAND_GRAPH_HINTS[path] = CommandHint(category, scope, tuple(next_commands))
