"""Stateless rendering / formatting / introspection helpers.

Extracted from ``cli.py`` so the parser entry point stays focused on
wiring argparse to handlers. None of these helpers issue subprocess or
network calls — they format Python values for stdout or build dict
records for the JSON command graph.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..models import CommandHint, DiscoveryRecord, ModuleChange, OutdatedReport, SearchResult
from ..project_config import resolve_app_dir
from ._hints import _COMMAND_GRAPH_HINTS


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _command_hint(path: list[str]) -> CommandHint | None:
    key = " ".join(path)
    return _COMMAND_GRAPH_HINTS.get(key)


def _argument_record(action: argparse.Action) -> dict[str, Any]:
    record: dict[str, Any] = {
        "dest": action.dest,
        "required": bool(getattr(action, "required", False)),
    }
    if getattr(action, "help", None) not in (None, argparse.SUPPRESS):
        record["help"] = action.help
    if getattr(action, "metavar", None) is not None:
        record["metavar"] = _json_safe(action.metavar)
    if getattr(action, "choices", None) is not None:
        record["choices"] = _json_safe(list(action.choices))
    if getattr(action, "default", argparse.SUPPRESS) is not argparse.SUPPRESS:
        record["default"] = _json_safe(action.default)
    if getattr(action, "nargs", None) is not None:
        record["nargs"] = _json_safe(action.nargs)
    if action.option_strings:
        record["kind"] = "option"
        record["flags"] = list(action.option_strings)
    else:
        record["kind"] = "positional"
        record["name"] = action.dest
    return record


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _command_record(
    parser: argparse.ArgumentParser,
    *,
    path: list[str],
    summary: str | None = None,
) -> dict[str, Any]:
    options: list[dict[str, Any]] = []
    positionals: list[dict[str, Any]] = []
    subcommands: list[dict[str, Any]] = []

    subparsers = _subparsers_action(parser)
    help_lookup: dict[str, str | None] = {}
    if subparsers is not None:
        for choice_action in subparsers._choices_actions:
            help_lookup[choice_action.dest] = choice_action.help

    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        record = _argument_record(action)
        if record["kind"] == "option":
            options.append(record)
        else:
            positionals.append(record)

    if subparsers is not None:
        for name in sorted(subparsers.choices.keys()):
            subcommands.append(
                _command_record(
                    subparsers.choices[name],
                    path=path + [name],
                    summary=help_lookup.get(name),
                )
            )

    record = {
        "name": path[-1] if path else "nsx",
        "command": "nsx" if not path else f"nsx {' '.join(path)}",
        "path": path,
        "summary": summary,
        "description": parser.description,
        "usage": parser.format_usage().strip(),
        "arguments": {
            "positionals": positionals,
            "options": options,
        },
        "subcommands": subcommands,
    }
    hint = _command_hint(path)
    if hint is not None:
        record.update(hint.to_dict())
    return record


def _command_graph(parser: argparse.ArgumentParser) -> dict[str, Any]:
    subparsers = _subparsers_action(parser)
    commands: list[dict[str, Any]] = []
    help_lookup: dict[str, str | None] = {}
    if subparsers is not None:
        for choice_action in subparsers._choices_actions:
            help_lookup[choice_action.dest] = choice_action.help
        for name in sorted(subparsers.choices.keys()):
            commands.append(
                _command_record(
                    subparsers.choices[name],
                    path=[name],
                    summary=help_lookup.get(name),
                )
            )

    graph = {
        "command": "nsx",
        "summary": parser.description,
        "workflow": {
            "recommended_start": ["nsx doctor", "nsx create-app"],
            "typical_lifecycle": [
                "nsx create-app",
                "nsx configure",
                "nsx build",
                "nsx flash",
                "nsx view",
                "nsx module add",
            ],
        },
        "commands": commands,
    }
    hint = _command_hint([])
    if hint is not None:
        graph.update(hint.to_dict())
    return graph


def _render_outdated_report(report: OutdatedReport) -> None:
    """Render an :class:`OutdatedReport` to stdout (text format)."""

    rows = [
        (m.name, m.constraint, m.locked[:10], m.upstream[:10], str(m.status))
        for m in report.checked
    ]
    if not rows and not report.skipped:
        print("No git modules to check.")
        return

    name_w = max((len(r[0]) for r in rows), default=4)
    cons_w = max((len(r[1]) for r in rows), default=10)
    header = f"{'module'.ljust(name_w)}  {'constraint'.ljust(cons_w)}  {'locked'.ljust(10)}  {'upstream'.ljust(10)}  status"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r[0].ljust(name_w)}  {r[1].ljust(cons_w)}  {r[2].ljust(10)}  {r[3].ljust(10)}  {r[4]}"
        )

    if report.skipped:
        print()
        for skip in report.skipped:
            print(f"skipped: {skip.name} ({skip.reason})")

    print()
    outdated = report.outdated
    if outdated:
        names = ", ".join(m.name for m in outdated)
        print(f"{len(outdated)} outdated: {names}")
        print("Run `nsx update` (all) or `nsx update --module <name>` to refresh.")
    else:
        print("All git modules are up-to-date with their constraints.")


def _render_module_changes(
    changes: list[ModuleChange], *, requested: str | None, verb: str
) -> None:
    """Render a list of :class:`ModuleChange` records to stdout.

    ``verb`` is one of ``"add"`` / ``"remove"`` / ``"update"`` /
    ``"register"`` and seeds the human-readable summary line. When
    ``requested`` is the user-supplied module name we surface it first
    so cascaded transitive changes are obvious.
    """

    prefix = "[dry-run] " if any(c.dry_run for c in changes) else ""
    if not changes:
        if verb == "update":
            print(f"{prefix}No modules updated.")
        else:
            print(f"{prefix}No changes.")
        return

    primary = next(
        (c for c in changes if requested and c.name == requested),
        changes[0],
    )
    others = [c for c in changes if c is not primary]

    def _summary(c: ModuleChange) -> str:
        if c.action == "added":
            after = f" -> {c.after}" if c.after else ""
            return f"added '{c.name}'{after}"
        if c.action == "removed":
            return f"removed '{c.name}'"
        if c.action == "updated":
            return f"updated '{c.name}': {c.before or '?'} -> {c.after or '?'}"
        return f"noop '{c.name}' ({c.before or 'n/a'})"

    print(f"{prefix}{_summary(primary)}")
    for c in others:
        print(f"{prefix}  also {_summary(c)}")


def _render_module_init(change: ModuleChange, module_dir: Path) -> None:
    """Render the result of ``nsx module init`` with next-step hints."""

    print(f"Created module skeleton '{change.name}' (version {change.after}) at: {module_dir}")
    metadata_path = module_dir / "nsx-module.yaml"
    print("Next steps:")
    print("  1) Review nsx-module.yaml and fill in summary, capabilities, and compatibility")
    print(f"  2) Run `nsx module validate {metadata_path}`")
    print(
        "  3) Register it into an app with `nsx module register "
        f"{change.name} --metadata {metadata_path} --project {change.name} "
        f"--project-local-path {module_dir} --app-dir <app-dir>`"
    )


def _resolve_cli_app_dir(app_dir_arg: str | None) -> Path | None:
    """Resolve CLI --app-dir to a Path, or None when not supplied."""

    if app_dir_arg is None:
        return None
    return resolve_app_dir(app_dir_arg)


def _print_module_detail(record: DiscoveryRecord) -> None:
    print(f"Module: {record.name}")
    print(f"Project: {record.project}")
    print(f"Revision: {record.revision}")
    print(f"Metadata: {record.metadata}")
    print(f"Enabled: {'yes' if record.enabled else 'no'}")
    if not record.metadata_available:
        if record.metadata_error is not None:
            print(f"Metadata available: no ({record.metadata_error})")
        return

    module = record.module
    if module is None:
        return
    print(f"Type: {module['type']}")
    print(f"Version: {module['version']}")
    if "category" in module:
        print(f"Category: {module['category']}")
    if "provider" in module:
        print(f"Provider: {module['provider']}")
    if record.summary is not None:
        print(f"Summary: {record.summary}")
    if record.capabilities is not None:
        print(f"Capabilities: {', '.join(record.capabilities)}")
    if record.use_cases is not None:
        print(f"Use cases: {', '.join(record.use_cases)}")
    build = record.build
    depends = record.depends
    compatibility = record.compatibility
    if build is not None:
        print(f"Targets: {', '.join(build['cmake']['targets'])}")
    if depends is not None:
        print(f"Required deps: {', '.join(depends['required']) or '(none)'}")
        print(f"Optional deps: {', '.join(depends['optional']) or '(none)'}")
    if compatibility is not None:
        print(f"Boards: {', '.join(compatibility['boards'])}")
        print(f"SoCs: {', '.join(compatibility['socs'])}")
        print(f"Toolchains: {', '.join(compatibility['toolchains'])}")
    if record.provides is not None:
        print("Provides:")
        print(json.dumps(record.provides, indent=2, sort_keys=True))


def _print_module_search_results(
    results: list[SearchResult], target_context: dict[str, str] | None
) -> None:
    if target_context:
        print(
            "Target context: "
            + ", ".join(f"{key}={value}" for key, value in target_context.items())
        )
    if not results:
        print("No modules matched the query.")
        return

    for result in results:
        compat_text = (
            "compatible"
            if result.compatible is True
            else "incompatible"
            if result.compatible is False
            else "compatibility-unknown"
        )
        print(f"- {result.name} (score={result.score}, {compat_text})")
        if result.metadata_available:
            module = result.module
            if module is not None:
                build = result.build
                targets = ", ".join(build["cmake"]["targets"]) if build is not None else ""
                print(f"  type={module['type']} project={result.project} targets={targets}")
        if result.matches:
            preview = ", ".join(f"{m.field}={m.value}" for m in result.matches[:4])
            print(f"  matched: {preview}")


def _format_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{n} B"
