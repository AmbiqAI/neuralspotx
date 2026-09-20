# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Write the committed module and board snapshots the docs site builds from.

Module manifests live in the module repositories, not in this one, so the only
way to read all fifty is over the network. The site build must not do that, so
this script does it once and commits the result: ``astro-site/src/data``
carries ``modules.json`` and ``boards.json``, and ``--check`` regenerates both
in memory and exits non-zero when the tree disagrees with them.

Everything it reads comes from the public API: ``list_modules`` in
registry-only mode for the catalog, ``load_registry`` for the projects and SoC
families, ``validate_module_metadata`` for each manifest it fetches, and
``load_board_descriptors`` for the board matrix.

One project in the registry is private (``helia-dsp``), so a run without
credentials cannot read its manifest. ``--check`` reports those modules as not
checked and compares the rest rather than failing on an access problem it
cannot distinguish from drift; writing a snapshot with a manifest missing
needs ``--allow-missing``.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from neuralspotx import list_modules, load_registry, validate_module_metadata
from neuralspotx.board_descriptors import load_board_descriptors
from neuralspotx.constants import BOARDS

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODULES_OUT = REPO_ROOT / "astro-site/src/data/modules.json"
DEFAULT_BOARDS_OUT = REPO_ROOT / "astro-site/src/data/boards.json"
# Under astro-site/.astro, which the site already ignores, because the clones
# are a build input with the same lifetime as the rest of that directory.
DEFAULT_WORKSPACE = REPO_ROOT / "astro-site/.astro/module-sources"

# Recorded per module so a reader of the snapshot can tell a field that is
# absent from the manifest apart from a manifest this run could not read.
SOURCE_PACKAGED = "packaged"
SOURCE_GIT = "git"
SOURCE_UNAVAILABLE = "unavailable"

# Fields that come out of a module's nsx-module.yaml. --check can only compare
# these for a module whose manifest the run actually read.
MANIFEST_FIELDS = (
    "type",
    "category",
    "provider",
    "version",
    "summary",
    "capabilities",
    "use_cases",
    "anti_use_cases",
    "agent_keywords",
    "provides",
    "depends",
    "compatibility",
    "constraints",
    "example_refs",
    "integrations",
)


class GenerationError(RuntimeError):
    """A snapshot could not be produced from the tree and the network."""


def _git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GenerationError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip() or result.stdout.strip()}"
        )


def manifest_relpath(metadata: str, project_path: str | None) -> Path:
    """Return a module's manifest path inside its project's repository.

    The registry records the manifest path as the app sees it, which for a
    project checked out at its own ``path`` is that prefix plus the path inside
    the repository, and for a project that holds several modules side by side
    is the path inside the repository already. Stripping the prefix when it is
    there is the same rule the resolver applies.
    """

    path = Path(metadata)
    if project_path:
        prefix = Path(project_path).parts
        if path.parts[: len(prefix)] == prefix:
            return Path(*path.parts[len(prefix) :])
    return path


def browse_url(clone_url: str) -> str:
    """Return the human-facing repository URL for a registry project."""

    return clone_url.removesuffix(".git")


def fetch_manifests(
    wanted: dict[tuple[str, str], list[tuple[str, Path]]],
    registry: dict[str, Any],
    workspace: Path,
) -> tuple[dict[str, Path], dict[str, str]]:
    """Check out every wanted manifest and return its path, or why it is absent.

    *wanted* maps a ``(project, revision)`` pair to the ``(module name,
    manifest path in the repository)`` pairs it has to supply. The key carries
    the revision because a module may pin one of its own ahead of the project's
    (``nsx-npu`` sits on a later SDK tag than the rest of that project), so one
    project can need more than one checkout. The clone is shallow, blobless and
    sparse: the only blobs fetched are the manifests themselves, which keeps
    the largest project in the registry under a megabyte.
    """

    found: dict[str, Path] = {}
    failed: dict[str, str] = {}

    for (project, revision), entries in sorted(wanted.items()):
        project_entry = registry["projects"].get(project)
        if project_entry is None:
            for module, _ in entries:
                failed[module] = f"project {project!r} is not in the registry"
            continue

        url = project_entry["url"]
        clone = workspace / project / revision.replace("/", "_")
        stamp = clone / ".nsx-docs-revision"
        paths = sorted({str(relpath) for _, relpath in entries})

        try:
            if not (stamp.exists() and stamp.read_text(encoding="utf-8").strip() == revision):
                # A pinned revision never moves, so the clone is either the one
                # the pin asks for or it is thrown away: reusing a checkout at
                # a different revision is what would make a run irreproducible.
                shutil.rmtree(clone, ignore_errors=True)
                clone.mkdir(parents=True, exist_ok=True)
                _git(["init", "-q", "."], cwd=clone)
                _git(["remote", "add", "origin", url], cwd=clone)
                _git(["sparse-checkout", "set", "--no-cone", *(f"/{p}" for p in paths)], cwd=clone)
                _git(
                    ["fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", revision],
                    cwd=clone,
                )
                _git(["checkout", "-q", "FETCH_HEAD"], cwd=clone)
                stamp.write_text(f"{revision}\n", encoding="utf-8")
        except GenerationError as exc:
            for module, _ in entries:
                failed[module] = str(exc)
            continue

        for module, relpath in entries:
            candidate = clone / relpath
            if candidate.exists():
                found[module] = candidate
            else:
                failed[module] = f"{relpath} is not in {project} at {revision}"

    return found, failed


def build_modules(
    *,
    workspace: Path,
    offline: bool = False,
) -> dict[str, Any]:
    """Build the module snapshot from the registry and the module manifests."""

    registry = load_registry()
    records = list_modules(registry_only=True, include_metadata=True)

    wanted: dict[tuple[str, str], list[tuple[str, Path]]] = {}
    for record in records:
        if record.metadata_available or record.metadata is None:
            continue
        project_entry = registry["projects"].get(record.project, {})
        relpath = manifest_relpath(record.metadata, project_entry.get("path"))
        wanted.setdefault((record.project, record.revision), []).append((record.name, relpath))

    if offline:
        fetched: dict[str, Path] = {}
        failures = {
            module: "offline: the manifest was not fetched"
            for entries in wanted.values()
            for module, _ in entries
        }
    else:
        workspace.mkdir(parents=True, exist_ok=True)
        fetched, failures = fetch_manifests(wanted, registry, workspace)

    modules: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: item.name):
        project_entry = registry["projects"].get(record.project, {})
        clone_url = project_entry.get("url", "")
        repo = browse_url(clone_url) if clone_url else None

        entry: dict[str, Any] = {
            "name": record.name,
            "slug": record.name,
            "project": record.project,
            "revision": record.revision,
            "metadata_path": record.metadata,
            "repo_url": repo,
            "source_url": f"{repo}/tree/{record.revision}" if repo else None,
        }

        if record.metadata_available:
            entry["manifest_source"] = SOURCE_PACKAGED
            entry["manifest_error"] = None
            entry.update(_manifest_fields(dataclasses.asdict(record)))
        elif record.name in fetched:
            data = validate_module_metadata(fetched[record.name])
            entry["manifest_source"] = SOURCE_GIT
            entry["manifest_error"] = None
            entry.update(_manifest_fields(data))
        else:
            entry["manifest_source"] = SOURCE_UNAVAILABLE
            entry["manifest_error"] = failures.get(record.name, "the manifest was not found")
            entry.update(_manifest_fields({}))

        modules.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "registry_schema_version": registry.get("schema_version"),
        "module_count": len(modules),
        "modules": modules,
    }


def _manifest_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Project an nsx-module.yaml body, or a DiscoveryRecord, onto the snapshot.

    A DiscoveryRecord carries the manifest's own top-level keys under the same
    names, so one projection serves both and the snapshot cannot disagree with
    itself depending on where a manifest was read from.
    """

    module = data.get("module") or {}
    depends = data.get("depends") or {}
    compatibility = data.get("compatibility") or {}
    return {
        "type": module.get("type"),
        "category": module.get("category"),
        "provider": module.get("provider"),
        "version": module.get("version"),
        "summary": data.get("summary"),
        "capabilities": list(data.get("capabilities") or []),
        "use_cases": list(data.get("use_cases") or []),
        "anti_use_cases": list(data.get("anti_use_cases") or []),
        "agent_keywords": list(data.get("agent_keywords") or []),
        "provides": data.get("provides") or {},
        "depends": {
            "required": list(depends.get("required") or []),
            "optional": list(depends.get("optional") or []),
        },
        "compatibility": {
            "boards": list(compatibility.get("boards") or []),
            "socs": list(compatibility.get("socs") or []),
            "toolchains": list(compatibility.get("toolchains") or []),
        },
        "constraints": data.get("constraints") or {},
        "example_refs": list(data.get("example_refs") or []),
        "integrations": data.get("integrations") or {},
    }


def build_boards() -> dict[str, Any]:
    """Build the board snapshot from the board descriptors and the registry."""

    registry = load_registry()
    descriptors = load_board_descriptors()
    families = registry.get("soc_families") or {}

    boards = []
    for order, name in enumerate(BOARDS):
        descriptor = descriptors[name]
        family = families.get(descriptor.soc) or {}
        boards.append({
            "order": order,
            "name": descriptor.name,
            "soc": descriptor.soc,
            "soc_family": descriptor.soc if descriptor.soc in families else None,
            "tier": descriptor.tier,
            "sdk_provider": descriptor.sdk_provider,
            "sdk_provider_module": family.get("provider"),
            "cpu": {
                "core": descriptor.cpu.core,
                "float_abi": descriptor.cpu.float_abi,
                "abi": descriptor.cpu.abi,
            },
            "toolchains": list(descriptor.toolchains),
            "registered": descriptor.registered,
        })

    soc_families = {
        soc: {
            "provider": family.get("provider"),
            "project": family.get("project"),
            "revision": family.get("revision"),
            "modules": list(family.get("modules") or []),
            "sdk_modules": list(family.get("sdk_modules") or []),
            "core_modules": list(family.get("core_modules") or []),
        }
        for soc, family in sorted(families.items())
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "board_count": len(boards),
        "boards": boards,
        "soc_families": soc_families,
    }


def serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def reconcile_unavailable(
    generated: dict[str, Any], committed: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Carry committed manifest fields over the ones this run could not read.

    A private project answers a credential-less run with an access error, which
    looks nothing like drift but would compare as if every manifest field had
    been deleted. Those modules are taken from the committed snapshot and named
    in the report instead, so the check still fails on a real change to every
    module it could read.
    """

    committed_by_name = {entry["name"]: entry for entry in committed.get("modules", [])}
    skipped: list[str] = []
    modules = []
    for entry in generated.get("modules", []):
        if entry.get("manifest_source") != SOURCE_UNAVAILABLE:
            modules.append(entry)
            continue
        previous = committed_by_name.get(entry["name"])
        if previous is None or previous.get("manifest_source") == SOURCE_UNAVAILABLE:
            modules.append(entry)
            continue
        merged = dict(entry)
        merged["manifest_source"] = previous["manifest_source"]
        merged["manifest_error"] = previous.get("manifest_error")
        for field in MANIFEST_FIELDS:
            merged[field] = previous.get(field)
        modules.append(merged)
        skipped.append(entry["name"])

    return {**generated, "modules": modules}, skipped


def diff_summary(label: str, generated: str, committed: str, *, context: int = 2) -> list[str]:
    """Return a bounded unified diff, so a wide drift still prints readably."""

    if generated == committed:
        return []
    diff = list(
        difflib.unified_diff(
            committed.splitlines(),
            generated.splitlines(),
            fromfile=f"{label} (committed)",
            tofile=f"{label} (regenerated)",
            n=context,
            lineterm="",
        )
    )
    changed = sum(1 for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---"))
    head = diff[:80]
    if len(diff) > 80:
        head.append(f"... {len(diff) - 80} more diff lines ({changed} changed lines in total)")
    return head


def check(modules_out: Path, boards_out: Path, *, workspace: Path, offline: bool) -> int:
    problems: list[str] = []
    for path in (modules_out, boards_out):
        if not path.exists():
            problems.append(f"{path} does not exist; run this script without --check")
    if problems:
        for problem in problems:
            print(f"build_module_data: {problem}", file=sys.stderr)
        return 1

    committed_modules = json.loads(modules_out.read_text(encoding="utf-8"))
    generated_modules, skipped = reconcile_unavailable(
        build_modules(workspace=workspace, offline=offline), committed_modules
    )
    generated_boards = build_boards()

    lines: list[str] = []
    lines += diff_summary(
        "modules.json", serialize(generated_modules), modules_out.read_text(encoding="utf-8")
    )
    lines += diff_summary(
        "boards.json", serialize(generated_boards), boards_out.read_text(encoding="utf-8")
    )

    if skipped:
        print(
            "build_module_data: manifest fields not checked for "
            f"{len(skipped)} module(s) whose project this run could not read: "
            f"{', '.join(sorted(skipped))}",
            file=sys.stderr,
        )

    if lines:
        print("build_module_data: the committed snapshot is out of date.", file=sys.stderr)
        for line in lines:
            print(line, file=sys.stderr)
        print(
            "build_module_data: run 'uv run python scripts/docs/build_module_data.py' and commit the result.",
            file=sys.stderr,
        )
        return 1

    unavailable = [
        entry["name"]
        for entry in committed_modules.get("modules", [])
        if entry.get("manifest_source") == SOURCE_UNAVAILABLE
    ]
    print(
        f"build_module_data: snapshot is current, {generated_modules['module_count']} modules and "
        f"{generated_boards['board_count']} boards"
        + (f", {len(unavailable)} without a manifest" if unavailable else "")
        + (f", {len(skipped)} not checked" if skipped else "")
        + "."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modules-out", type=Path, default=DEFAULT_MODULES_OUT)
    parser.add_argument("--boards-out", type=Path, default=DEFAULT_BOARDS_OUT)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="where the sparse module-project clones are kept between runs",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="read only the manifests this repository ships and fetch nothing",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="write the snapshot even though a manifest could not be read",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and exit 1 when the committed snapshot differs",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check(
            args.modules_out, args.boards_out, workspace=args.workspace, offline=args.offline
        )

    modules = build_modules(workspace=args.workspace, offline=args.offline)
    boards = build_boards()

    unavailable = [
        entry["name"]
        for entry in modules["modules"]
        if entry["manifest_source"] == SOURCE_UNAVAILABLE
    ]
    if unavailable and not args.allow_missing:
        print(
            "build_module_data: no manifest for "
            f"{', '.join(unavailable)}. Authenticate to the projects that hold them, or pass "
            "--allow-missing to write a snapshot without their manifest fields.",
            file=sys.stderr,
        )
        for name in unavailable:
            entry = next(item for item in modules["modules"] if item["name"] == name)
            print(f"  {name}: {entry['manifest_error']}", file=sys.stderr)
        return 1

    for path, payload in ((args.modules_out, modules), (args.boards_out, boards)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialize(payload), encoding="utf-8")

    print(
        f"build_module_data: wrote {modules['module_count']} modules to {args.modules_out} and "
        f"{boards['board_count']} boards to {args.boards_out}"
        + (f" ({len(unavailable)} without a manifest)" if unavailable else "")
        + "."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
