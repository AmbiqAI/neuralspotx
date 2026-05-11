"""Human-readable registry-table printer used by the CLI."""

from __future__ import annotations

from typing import Any

from ..metadata import registry_entry_for_module


def _print_module_table(
    registry: dict[str, Any],
    enabled: set[str],
    *,
    heading: str = "NSX modules in the active registry (* = enabled for this app):",
) -> None:
    print(heading)
    for name in sorted(registry["modules"].keys()):
        marker = "*" if name in enabled else " "
        entry = registry_entry_for_module(registry, name)
        print(f"  {marker} {name}  (project={entry.project}, revision={entry.revision})")
