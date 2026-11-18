"""Public helpers for packaged registry and starter-profile access."""

from __future__ import annotations

import functools
import importlib.resources as resources
from copy import deepcopy
from typing import Any

from ..metadata import load_registry_lock, registry_entry_for_module


@functools.lru_cache(maxsize=1)
def _load_packaged_registry() -> dict[str, Any]:
    """Load and cache the private packaged registry, including derived profiles."""
    registry_resource = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(registry_resource) as registry_path:
        return load_registry_lock(registry_path)


def load_registry() -> dict[str, Any]:
    """Return an independent snapshot of the packaged NSX registry.

    Includes derived starter profiles. Nested dictionaries and lists may be
    modified without affecting later calls or other registry helpers. The
    packaged data is cached privately; no network or git operations are performed.
    """
    return deepcopy(_load_packaged_registry())


def starter_profile(board: str) -> dict[str, Any] | None:
    """Return an independent ``{board}_minimal`` profile, or ``None`` if absent.

    Mutating the returned profile does not change the packaged registry or
    subsequent results from either public helper.
    """
    profiles = _load_packaged_registry().get("starter_profiles", {})
    return deepcopy(profiles.get(f"{board}_minimal"))


def registry_module_project(name: str) -> str | None:
    """Resolve a module name to its owning project via the packaged registry.

    Returns ``None`` when the module has no packaged registry entry (for
    example, a local opaque module supplied by the caller).
    """
    try:
        return registry_entry_for_module(_load_packaged_registry(), name).project
    except (KeyError, ValueError):
        return None
