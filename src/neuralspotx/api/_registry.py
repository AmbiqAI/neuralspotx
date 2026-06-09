"""Public helpers for packaged registry and starter-profile access."""

from __future__ import annotations

import functools
import importlib.resources as resources
from typing import Any

from ..metadata import load_registry_lock, registry_entry_for_module


@functools.lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    """Return the packaged NSX registry with derived starter profiles.

    The result is loaded from the installed ``registry.lock.yaml`` and cached
    in-process. No network or git operations are performed.
    """
    registry_resource = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(registry_resource) as registry_path:
        return load_registry_lock(registry_path)


def starter_profile(board: str) -> dict[str, Any] | None:
    """Return the ``{board}_minimal`` starter profile, or ``None`` if absent."""
    profiles = load_registry().get("starter_profiles", {})
    return profiles.get(f"{board}_minimal")


def registry_module_project(name: str) -> str | None:
    """Resolve a module name to its owning project via the packaged registry.

    Returns ``None`` when the module has no packaged registry entry (for
    example, a local opaque module supplied by the caller).
    """
    try:
        return registry_entry_for_module(load_registry(), name).project
    except (KeyError, ValueError):
        return None