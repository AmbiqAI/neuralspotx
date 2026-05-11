"""Module change records emitted by ``api`` mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ------------------------------------------------------------------
# Module change records (api.add_module / remove_module / update_modules /
# register_module / init_module)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ModuleChange:
    """One state-change applied to a module by an api.* mutation.

    Attributes:
        name: Module name.
        before: The recorded revision (or ``None`` when the module did
            not exist beforehand). May be ``None`` for ``init_module``
            since there is no app-side state.
        after: The resolved revision after the operation (or ``None``
            when the module was removed).
        action: One of ``"added"``, ``"removed"``, ``"updated"``,
            ``"noop"``. ``"added"`` covers ``add_module``/
            ``register_module``/``init_module`` and any transitive
            dependencies pulled in. ``"removed"`` covers cascaded
            removals. ``"updated"`` is recorded by ``update_modules``
            when the resolved revision changed; ``"noop"`` when it did
            not.
        dry_run: ``True`` when the change was predicted by a
            ``dry_run=True`` call and not actually applied.
    """

    name: str
    before: str | None
    after: str | None
    action: str
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "action": self.action,
            "dry_run": self.dry_run,
        }
