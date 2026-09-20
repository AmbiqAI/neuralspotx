# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Reduce a griffe dump of ``neuralspotx`` to the documented public surface.

``helia-ui-pyref`` renders one page per module in the dump and applies
``--filter`` to member names only, so a raw dump yields a page for every
private ``_module`` and leaves cross-references to re-exported types
dangling at their private definition path. Both are upstream gaps
(AmbiqAI/helia-ui#120 and #121); until they close, this script rewrites the
dump so that the tree pyref sees already *is* the public surface:

* every ``neuralspotx.__all__`` name is resolved through its alias chain to
  the concrete definition and rehomed onto the public module that exports it,
* private modules are dropped entirely,
* docstring cross-references are retargeted from the old (often private)
  paths to the rehomed public paths.

Rehoming is deliberate rather than inferred: ``HOME_MODULES`` lists the
public modules a symbol may be documented under, in preference order, and
``tests/test_reference_generation.py`` asserts the chosen home really
re-exports the same object.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

PACKAGE = "neuralspotx"

# Public modules a public name may be documented under, deepest-preferred.
# A name that none of these re-export is documented on the package root,
# which is the only public import path for symbols defined in private
# modules (the errors and the structured emitter).
HOME_MODULES = (
    f"{PACKAGE}.api",
    f"{PACKAGE}.models",
    f"{PACKAGE}.nsx_lock",
    f"{PACKAGE}.operations",
)

# Sidebar grouping. pyref has no grouping control (AmbiqAI/helia-ui#74), so
# the category travels beside the model and the site builds the grouped
# sidebar from it.
CATEGORY_ERRORS = "errors"
CATEGORY_MODELS = "models"
CATEGORY_FUNCTIONS = "functions"
CATEGORY_EMITTERS = "emitters"

EMITTER_NAMES = frozenset({"Emitter", "Event", "default_emitter"})

GROUP_ORDER = (CATEGORY_ERRORS, CATEGORY_MODELS, CATEGORY_FUNCTIONS, CATEGORY_EMITTERS)


def _is_private_path(path: str) -> bool:
    return any(part.startswith("_") for part in path.split(".")[1:])


def _index(dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map every object in the dump to its canonical dotted path."""
    index: dict[str, dict[str, Any]] = {}

    def walk(obj: dict[str, Any], path: str) -> None:
        index[path] = obj
        for name, member in (obj.get("members") or {}).items():
            if isinstance(member, dict):
                walk(member, f"{path}.{name}")

    for name, obj in dump.items():
        walk(obj, name)
    return index


def _resolve(path: str, index: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    """Follow an alias chain to the concrete definition it names."""
    seen: set[str] = set()
    current = path
    while True:
        obj = index.get(current)
        if obj is None or obj.get("kind") != "alias":
            return (current, obj) if obj is not None else None
        target = obj.get("target_path")
        if not isinstance(target, str) or target in seen:
            return None
        seen.add(current)
        current = target


def _repath(obj: dict[str, Any], new_path: str) -> None:
    """Rewrite ``path`` through a rehomed subtree so anchors match the page."""
    obj["path"] = new_path
    for name, member in (obj.get("members") or {}).items():
        if isinstance(member, dict):
            _repath(member, f"{new_path}.{name}")


def _module_shell(module: dict[str, Any]) -> dict[str, Any]:
    """Copy a module node without its members or submodules."""
    shell = {k: v for k, v in module.items() if k != "members"}
    shell["members"] = {}
    return shell


def _categorize(name: str, obj: dict[str, Any], error_names: set[str]) -> str:
    if name in error_names:
        return CATEGORY_ERRORS
    if name in EMITTER_NAMES:
        return CATEGORY_EMITTERS
    if obj.get("kind") == "function":
        return CATEGORY_FUNCTIONS
    if obj.get("kind") == "attribute":
        return CATEGORY_MODELS
    return CATEGORY_MODELS


def _annotation_names(node: Any, out: set[str]) -> None:
    """Collect every ``ExprName`` identifier inside a griffe annotation."""
    if isinstance(node, dict):
        if node.get("cls") == "ExprName" and isinstance(node.get("name"), str):
            out.add(node["name"])
        for value in node.values():
            _annotation_names(value, out)
    elif isinstance(node, list):
        for value in node:
            _annotation_names(value, out)


def _signature_types(obj: dict[str, Any]) -> set[str]:
    """Every identifier a reader meets in a symbol's rendered signature.

    That is parameters and return types, the annotation on an attribute (a
    dataclass field is an attribute, so this is where most of them come from)
    and the same again for nested classes.
    """
    names: set[str] = set()
    for parameter in obj.get("parameters") or []:
        _annotation_names(parameter.get("annotation"), names)
    _annotation_names(obj.get("returns"), names)
    _annotation_names(obj.get("annotation"), names)
    for base in obj.get("bases") or []:
        _annotation_names(base, names)
    for member in (obj.get("members") or {}).values():
        if isinstance(member, dict) and member.get("kind") in {"function", "attribute", "class"}:
            names |= _signature_types(member)
    return names


def _find_definition(
    name: str, index: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]] | None:
    """Locate a definition anywhere in the dump by its leaf name.

    A type named in a public signature is usually not re-exported from the
    package root, so probing ``neuralspotx.<name>`` alone misses it. Prefer a
    definition in a public module, then the shallowest path, so the choice is
    deterministic.
    """
    candidates = [
        path
        for path, obj in index.items()
        if path.rsplit(".", 1)[-1] == name
        and obj.get("kind") in {"class", "attribute"}
        and obj.get("kind") != "alias"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (_is_private_path(path), path.count("."), path))
    return candidates[0], index[candidates[0]]


def _rewrite_crossrefs(node: Any, remap: dict[str, str]) -> int:
    """Retarget ``[Text][old.path]`` docstring links onto rehomed paths."""
    rewrites = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "value" and isinstance(value, str):
                new = value
                for old, fresh in remap.items():
                    token = f"][{old}]"
                    if token in new:
                        new = new.replace(token, f"][{fresh}]")
                if new != value:
                    node[key] = new
                    rewrites += 1
            else:
                rewrites += _rewrite_crossrefs(value, remap)
    elif isinstance(node, list):
        for value in node:
            rewrites += _rewrite_crossrefs(value, remap)
    return rewrites


def build(
    dump: dict[str, Any],
    public_names: list[str],
    exported_by: dict[str, frozenset[str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    index = _index(dump)
    root = dump[PACKAGE]

    error_names = {
        name
        for name in public_names
        if (resolved := _resolve(f"{PACKAGE}.{name}", index))
        and _resolve_is_error(resolved[0], resolved[1], index)
    }

    homes: dict[str, str] = {}
    concrete: dict[str, dict[str, Any]] = {}
    origins: dict[str, str] = {}
    for name in public_names:
        resolved = _resolve(f"{PACKAGE}.{name}", index)
        if resolved is None:
            raise SystemExit(f"prune_griffe: cannot resolve {PACKAGE}.{name} in the dump")
        origin, obj = resolved
        home = PACKAGE
        # Errors and the emitter are defined in private modules and a few are
        # incidentally re-exported from public ones; documenting them on the
        # package root keeps each category on one page and matches the only
        # import path the guides teach.
        if name in error_names or name in EMITTER_NAMES:
            homes[name] = home
            concrete[name] = obj
            origins[name] = origin
            continue
        for candidate in HOME_MODULES:
            # Membership in the candidate's own ``__all__`` is what makes the
            # home an intended public import path rather than an incidental
            # import that happens to be reachable.
            if name not in exported_by.get(candidate, frozenset()):
                continue
            candidate_resolved = _resolve(f"{candidate}.{name}", index)
            if candidate_resolved is not None and candidate_resolved[0] == origin:
                home = candidate
                break
        homes[name] = home
        concrete[name] = obj
        origins[name] = origin

    # Types named by public signatures that are not themselves exported keep
    # the reference resolvable instead of rendering as bare text.
    referenced: set[str] = set()
    for obj in concrete.values():
        referenced |= _signature_types(obj)
    supporting: dict[str, str] = {}
    for name in sorted(referenced - set(public_names)):
        resolved = _resolve(f"{PACKAGE}.{name}", index) or _find_definition(name, index)
        if resolved is None:
            # Names from the standard library and third-party packages are not
            # in this dump at all, which is expected; only a neuralspotx symbol
            # that cannot be placed is a defect.
            continue
        origin, obj = resolved
        if obj.get("kind") not in {"class", "attribute"}:
            continue
        if not origin.startswith(f"{PACKAGE}.") and origin != PACKAGE:
            continue
        # Document it on the public module that defines it where there is one,
        # otherwise on the package root alongside the errors and the emitter.
        owner = origin.rsplit(".", 1)[0]
        home = owner if owner in HOME_MODULES else PACKAGE
        supporting[name] = home
        concrete[name] = obj
        origins[name] = origin
        homes[name] = home

    unplaced = sorted(
        name
        for name in referenced - set(public_names) - set(supporting)
        if (found := _find_definition(name, index)) is not None
        and (found[0] == PACKAGE or found[0].startswith(f"{PACKAGE}."))
    )
    if unplaced:
        raise SystemExit(
            f"prune_griffe: {PACKAGE} types named by public signatures could not be "
            f"documented: {unplaced}"
        )

    categories = {
        name: _categorize(name, concrete[name], error_names)
        for name in homes
        if name not in supporting
    }

    pruned_root = _module_shell(root)
    modules: dict[str, dict[str, Any]] = {PACKAGE: pruned_root}
    for module_path in HOME_MODULES:
        if module_path not in homes.values():
            continue
        source = index.get(module_path)
        if source is None:
            continue
        shell = _module_shell(source)
        modules[module_path] = shell
        pruned_root["members"][module_path.rsplit(".", 1)[1]] = shell

    remap: dict[str, str] = {}
    catalog: list[dict[str, Any]] = []
    for name in sorted(homes):
        home = homes[name]
        obj = copy.deepcopy(concrete[name])
        obj["name"] = name
        # pyref derives a member's page and cross-reference href from its path,
        # so the path has to stay under the module the page documents. Grouping
        # by category therefore happens in the sidebar rather than in the tree.
        new_path = f"{home}.{name}"
        _repath(obj, new_path)
        modules[home]["members"][name] = obj
        for old in {origins[name], f"{PACKAGE}.{name}"}:
            if old != new_path:
                remap[old] = new_path
        if name in supporting:
            continue
        catalog.append({
            "name": name,
            "path": new_path,
            "module": home,
            "kind": obj.get("kind", "object"),
            "category": categories[name],
        })

    pruned = {PACKAGE: pruned_root}
    rewrites = _rewrite_crossrefs(pruned, remap)

    sidebar_meta = {
        "package": PACKAGE,
        "symbols": catalog,
        "supporting": sorted(supporting),
        "modules": sorted(modules),
        "crossReferenceRewrites": rewrites,
    }
    return pruned, sidebar_meta


def _resolve_is_error(path: str, obj: dict[str, Any], index: dict[str, dict[str, Any]]) -> bool:
    """True when a class is ``NSXError`` or inherits from it."""
    if obj.get("kind") != "class":
        return False
    if path.rsplit(".", 1)[-1] == "NSXError":
        return True
    for base in obj.get("bases") or []:
        base_name = base.get("name") if isinstance(base, dict) else base
        if isinstance(base_name, str) and base_name.endswith("Error"):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path, help="griffe dump JSON")
    parser.add_argument("--output", required=True, type=Path, help="pruned griffe dump JSON")
    parser.add_argument("--catalog", type=Path, help="write the symbol catalog JSON here")
    args = parser.parse_args(argv)

    import importlib

    import neuralspotx

    dump = json.loads(args.input.read_text(encoding="utf-8"))
    if PACKAGE not in dump:
        raise SystemExit(f"prune_griffe: {PACKAGE} missing from {args.input}")

    exported_by = {
        module_path: frozenset(getattr(importlib.import_module(module_path), "__all__", ()))
        for module_path in HOME_MODULES
    }
    pruned, catalog = build(dump, list(neuralspotx.__all__), exported_by)

    # Check before writing, so a leak cannot leave a bad dump on disk for the
    # next stage to pick up.
    leaked = [m for m in catalog["modules"] if _is_private_path(m)]
    leaked += [s["path"] for s in catalog["symbols"] if _is_private_path(s["path"])]
    if leaked:
        raise SystemExit(f"prune_griffe: private paths survived pruning: {sorted(set(leaked))}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(pruned, indent=1, sort_keys=True), encoding="utf-8")
    if args.catalog:
        args.catalog.parent.mkdir(parents=True, exist_ok=True)
        args.catalog.write_text(json.dumps(catalog, indent=2, sort_keys=True), encoding="utf-8")

    print(
        f"prune_griffe: {len(catalog['symbols'])} public symbols across "
        f"{len(catalog['modules'])} modules, {len(catalog['supporting'])} supporting types, "
        f"{catalog['crossReferenceRewrites']} cross-reference rewrites",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
