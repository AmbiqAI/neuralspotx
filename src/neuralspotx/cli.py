"""NSX CLI — create and manage bare-metal Ambiq applications."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import api, nsx_lock, operations
from ._errors import NSXConfigError, NSXError, NSXModuleError, NSXToolchainError
from ._logging import configure_logging
from .metadata import SUPPORTED_MODULE_TYPES, load_yaml, validate_nsx_module_metadata
from .models import (
    CommandCategory,
    CommandHint,
    CommandScope,
    DiscoveryRecord,
    ModuleChange,
    OutdatedReport,
    SearchResult,
)
from .module_discovery import (
    resolve_module_context,
    resolve_target_context,
)
from .module_registry import (
    _print_module_table,
)
from .project_config import (
    resolve_app_dir,
)
from .subprocess_utils import format_subprocess_error

_C = CommandCategory
_S = CommandScope

# Discovery hints declared via the ``@command_hint(path, ...)`` decorator on each
# ``cmd_*`` handler below. Group/root paths that have no dedicated handler
# (``""``, ``"module"``, ``"cache"``) are registered explicitly at the bottom
# of this module via :func:`_register_group_hint`.
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


_register_group_hint("", _C.ENTRYPOINT, _S.GLOBAL, "nsx doctor", "nsx create-app")
_COMMAND_GRAPH_HINTS["new"] = CommandHint(
    _C.APP_CREATION,
    _S.APP,
    ("nsx configure", "nsx module list", "nsx module add"),
    alias_for="nsx create-app",
)
_register_group_hint(
    "module",
    _C.MODULES,
    _S.APP,
    "nsx module list",
    "nsx module describe",
    "nsx module init <module-dir>",
    "nsx module add",
)
_register_group_hint("cache", _C.MAINTENANCE, _S.GLOBAL, "nsx cache info", "nsx cache clean")


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


@command_hint(
    "commands",
    _C.DISCOVERY,
    _S.GLOBAL,
    "nsx module list --json",
    "nsx module describe <module> --json",
)
def cmd_commands(args: argparse.Namespace) -> None:
    graph = _command_graph(_build_parser())
    if args.json:
        print(json.dumps(graph, indent=2, sort_keys=True))
        return

    print("NSX command graph")
    for record in graph["commands"]:
        summary = record.get("summary") or ""
        print(f"- {record['command']}: {summary}")
        next_commands = record.get("next_commands", [])
        if next_commands:
            print(f"  next: {', '.join(next_commands)}")


@command_hint(
    "create-app",
    _C.APP_CREATION,
    _S.APP,
    "nsx configure",
    "nsx module list",
    "nsx module add",
)
def cmd_create_app(args: argparse.Namespace) -> None:
    api.create_app(
        Path(args.app_dir).expanduser().resolve(),
        board=args.board,
        soc=args.soc,
        force=args.force,
        no_bootstrap=args.no_bootstrap,
    )


@command_hint("doctor", _C.DIAGNOSTICS, _S.ENVIRONMENT, "nsx create-app", "nsx configure")
def cmd_doctor(args: argparse.Namespace) -> None:
    report = api.doctor()
    if not report.ok:
        raise NSXToolchainError("One or more required tools are missing or misconfigured.")


@command_hint(
    "configure",
    _C.BUILD,
    _S.APP,
    "nsx build",
    "nsx flash",
    "nsx view",
    "nsx module list",
)
def cmd_configure(args: argparse.Namespace) -> None:
    api.configure_app(
        resolve_app_dir(args.app_dir),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("build", _C.BUILD, _S.APP, "nsx flash", "nsx view", "nsx clean")
def cmd_build(args: argparse.Namespace) -> None:
    api.build_app(
        resolve_app_dir(args.app_dir),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        target=args.target,
        jobs=args.jobs,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("flash", _C.DEPLOY, _S.APP, "nsx view")
def cmd_flash(args: argparse.Namespace) -> None:
    api.flash_app(
        resolve_app_dir(args.app_dir),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        jobs=args.jobs,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("view", _C.DEPLOY, _S.APP, "nsx build", "nsx flash")
def cmd_view(args: argparse.Namespace) -> None:
    api.view_app(
        resolve_app_dir(args.app_dir),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        reset_on_open=not args.no_reset_on_open,
        reset_delay_ms=args.reset_delay_ms,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("clean", _C.BUILD, _S.APP, "nsx configure", "nsx build")
def cmd_clean(args: argparse.Namespace) -> None:
    api.clean_app(
        resolve_app_dir(args.app_dir),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        full=args.full,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("lock", _C.MODULES, _S.APP, "nsx sync", "nsx configure", "nsx build")
def cmd_lock(args: argparse.Namespace) -> None:
    # `--module X` re-resolves only the named module(s); per its `--help`
    # text it implies `--update` (the modules filter is a no-op without it).
    update = bool(args.update) or bool(args.modules)
    api.lock_app(
        resolve_app_dir(args.app_dir),
        update=update,
        modules=list(args.modules) if args.modules else None,
        check=bool(getattr(args, "check", False)),
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("sync", _C.MODULES, _S.APP, "nsx configure", "nsx build", "nsx flash")
def cmd_sync(args: argparse.Namespace) -> None:
    api.sync_app(
        resolve_app_dir(args.app_dir),
        frozen=bool(args.frozen),
        force=bool(args.force),
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("outdated", _C.MODULES, _S.APP, "nsx update", "nsx lock --update")
def cmd_outdated(args: argparse.Namespace) -> None:
    report = api.outdated_app(
        resolve_app_dir(args.app_dir),
        timeout_s=getattr(args, "timeout", None),
    )
    if getattr(args, "json", False):
        import json as _json

        print(_json.dumps(report.to_dict(), indent=2))
    else:
        _render_outdated_report(report)
    if args.exit_code and report.outdated_count:
        raise NSXError(1)


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


@command_hint("update", _C.MODULES, _S.APP, "nsx configure", "nsx build", "nsx flash")
def cmd_update(args: argparse.Namespace) -> None:
    api.update_app(
        resolve_app_dir(args.app_dir),
        modules=list(args.modules) if args.modules else None,
        timeout_s=getattr(args, "timeout", None),
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


@command_hint(
    "module search",
    _C.MODULES,
    _S.APP,
    "nsx module describe <module>",
    "nsx module add <module>",
    "nsx configure",
)
def cmd_module_search(args: argparse.Namespace) -> None:
    app_dir = _resolve_cli_app_dir(args.app_dir)
    results = api.search_modules(
        args.query,
        app_dir=app_dir,
        board=args.board,
        soc=args.soc,
        toolchain=args.toolchain,
        include_incompatible=args.include_incompatible,
    )
    if args.json:
        target_ctx = resolve_target_context(
            app_dir=app_dir,
            board=args.board,
            soc=args.soc,
            toolchain=args.toolchain,
        )
        _, _, resolved_app, scope = resolve_module_context(app_dir=app_dir)
        payload = {
            "scope": scope,
            "app_dir": str(resolved_app) if resolved_app else None,
            "query": args.query,
            "target_context": target_ctx,
            "results": [r.to_dict() for r in results],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    target_ctx = resolve_target_context(
        app_dir=app_dir,
        board=args.board,
        soc=args.soc,
        toolchain=args.toolchain,
    )
    _print_module_search_results(results, target_ctx)


@command_hint(
    "module list",
    _C.MODULES,
    _S.APP,
    "nsx module describe <module>",
    "nsx module add <module>",
    "nsx module register <module>",
)
def cmd_module_list(args: argparse.Namespace) -> None:
    if args.app_dir is None and not args.registry_only:
        raise NSXConfigError("nsx module list requires --app-dir unless --registry-only is used")

    app_dir = None if args.registry_only else _resolve_cli_app_dir(args.app_dir)
    registry, enabled, resolved_app, scope = resolve_module_context(app_dir=app_dir)
    if args.json:
        records = api.list_modules(
            app_dir=resolved_app,
            registry_only=args.registry_only,
            include_metadata=True,
        )
        payload = {
            "scope": scope,
            "app_dir": str(resolved_app) if resolved_app else None,
            "modules": [r.to_dict() for r in records],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    _print_module_table(
        registry,
        enabled,
        heading=(
            "NSX modules in the packaged registry:"
            if scope == "packaged"
            else "NSX modules in the active registry (* = enabled for this app):"
        ),
    )


@command_hint(
    "module describe",
    _C.MODULES,
    _S.APP,
    "nsx module add <module>",
    "nsx configure",
    "nsx build",
)
def cmd_module_describe(args: argparse.Namespace) -> None:
    app_dir = _resolve_cli_app_dir(args.app_dir)
    _, _, resolved_app, scope = resolve_module_context(app_dir=app_dir)
    try:
        record = api.describe_module(args.module, app_dir=resolved_app)
    except ValueError as exc:
        raise NSXModuleError(str(exc)) from None

    if args.json:
        payload = {
            "scope": scope,
            "app_dir": str(resolved_app) if resolved_app else None,
            "module": record.to_dict(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    _print_module_detail(record)


@command_hint("module add", _C.MODULES, _S.APP, "nsx configure", "nsx build", "nsx flash")
def cmd_module_add(args: argparse.Namespace) -> None:
    changes = api.add_module(
        resolve_app_dir(args.app_dir),
        args.module,
        local=getattr(args, "local", False),
        vendored=getattr(args, "vendored", False),
        dry_run=args.dry_run,
    )
    _render_module_changes(changes, requested=args.module, verb="add")


@command_hint("module remove", _C.MODULES, _S.APP, "nsx configure", "nsx build")
def cmd_module_remove(args: argparse.Namespace) -> None:
    changes = api.remove_module(
        resolve_app_dir(args.app_dir),
        args.module,
        dry_run=args.dry_run,
    )
    _render_module_changes(changes, requested=args.module, verb="remove")


@command_hint("module update", _C.MODULES, _S.APP, "nsx configure", "nsx build")
def cmd_module_update(args: argparse.Namespace) -> None:
    changes = api.update_modules(
        resolve_app_dir(args.app_dir),
        module=args.module,
        dry_run=args.dry_run,
    )
    _render_module_changes(changes, requested=args.module, verb="update")


@command_hint(
    "module register",
    _C.MODULES,
    _S.APP,
    "nsx module add <module>",
    "nsx configure",
    "nsx build",
)
def cmd_module_register(args: argparse.Namespace) -> None:
    change = api.register_module(
        resolve_app_dir(args.app_dir),
        args.module,
        metadata=Path(args.metadata).expanduser(),
        project=args.project,
        project_url=args.project_url,
        project_revision=args.project_revision,
        project_path=args.project_path,
        project_local_path=Path(args.project_local_path).expanduser().resolve()
        if args.project_local_path
        else None,
        override=args.override,
        dry_run=args.dry_run,
    )
    _render_module_changes([change], requested=args.module, verb="register")


@command_hint(
    "module init",
    _C.MODULES,
    _S.FILESYSTEM,
    "nsx module validate <metadata>",
    "nsx module register <module>",
    "nsx module add <module>",
)
def cmd_module_init(args: argparse.Namespace) -> None:
    module_dir = Path(args.module_dir).expanduser().resolve()
    change = api.init_module(
        module_dir,
        module_name=args.name,
        module_type=args.type,
        summary=args.summary,
        version=args.version,
        dependencies=args.dependency,
        boards=args.board,
        socs=args.soc,
        toolchains=args.toolchain,
        force=args.force,
    )
    _render_module_init(change, module_dir)


@command_hint(
    "module validate",
    _C.MODULES,
    _S.GLOBAL,
    "nsx module register <module>",
    "nsx module add <module>",
)
def cmd_module_validate(args: argparse.Namespace) -> None:
    metadata_path = Path(args.metadata).expanduser().resolve()
    try:
        data = load_yaml(metadata_path)
    except ValueError as exc:
        raise NSXConfigError(str(exc)) from None
    try:
        validate_nsx_module_metadata(data, str(metadata_path))
    except ValueError as exc:
        raise NSXConfigError(f"Validation failed: {exc}") from None

    if args.json:
        print(
            json.dumps(
                {
                    "valid": True,
                    "path": str(metadata_path),
                    "module": data.get("module", {}).get("name"),
                },
                indent=2,
            )
        )
    else:
        module_name = data.get("module", {}).get("name", "(unknown)")
        print(f"Valid: {metadata_path} (module: {module_name})")


def _format_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{n} B"


@command_hint("cache info", _C.MAINTENANCE, _S.GLOBAL, "nsx cache clean")
def cmd_cache_info(args: argparse.Namespace) -> None:
    info = api.cache_info()

    if args.json:
        print(json.dumps(info.to_dict(), indent=2))
        return

    print(f"nsx module cache: {info.root}")
    status = "disabled (NSX_DISABLE_MODULE_CACHE set)" if info.disabled else "enabled"
    print(f"  status:  {status}")
    print(f"  entries: {info.entry_count}")
    if info.entries:
        print(f"  total:   {_format_bytes(info.total_size_bytes)}")


@command_hint("cache clean", _C.MAINTENANCE, _S.GLOBAL, "nsx sync")
def cmd_cache_clean(args: argparse.Namespace) -> None:
    if not args.yes:
        preview = api.clean_cache(dry_run=True)
        if preview.removed_count == 0:
            print(f"nsx module cache at {preview.root} is already empty.")
            return
        print(
            f"This will delete {preview.removed_count} cached module artifact(s) "
            f"under {preview.root}. Re-run with --yes to confirm."
        )
        return
    result = api.clean_cache()
    print(f"Removed {result.removed_count} cached module artifact(s).")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NSX helper for creating and building bare-metal Ambiq apps"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase CLI verbosity. Repeat for more detail.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress informational and warning logs (errors still surface).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_timeout(p: argparse.ArgumentParser) -> None:
        # Per-subprocess wall-clock budget.  Surfaced uniformly across
        # commands that shell out to git/cmake/ninja/JLinkExe so users
        # can bound CI/run time end-to-end.  Wired through api.py's
        # ``timeout_budget`` context manager.
        p.add_argument(
            "--timeout",
            type=float,
            default=None,
            metavar="SECONDS",
            help=(
                "Wall-clock budget per subprocess (seconds). "
                "Kills the whole process group on timeout."
            ),
        )

    p_new = sub.add_parser("create-app", help="Create a new standalone NSX app project")
    p_new.add_argument("app_dir", help="App directory to create")
    p_new.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new.add_argument(
        "--soc", default=None, help="Target SoC package suffix (default inferred from board)"
    )
    p_new.add_argument(
        "--force", action="store_true", help="Allow writing into a non-empty app directory"
    )
    p_new.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Create the app without initializing starter modules",
    )
    p_new.set_defaults(func=cmd_create_app)

    p_new_alias = sub.add_parser("new", help="Alias for create-app")
    p_new_alias.add_argument("app_dir", help="App directory to create")
    p_new_alias.add_argument("--board", default="apollo510_evb", help="Target board package suffix")
    p_new_alias.add_argument(
        "--soc", default=None, help="Target SoC package suffix (default inferred from board)"
    )
    p_new_alias.add_argument(
        "--force", action="store_true", help="Allow writing into a non-empty app directory"
    )
    p_new_alias.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="Create the app without initializing starter modules",
    )
    p_new_alias.set_defaults(func=cmd_create_app)

    p_doctor = sub.add_parser("doctor", help="Check the local NSX toolchain environment")
    p_doctor.set_defaults(func=cmd_doctor)

    p_commands = sub.add_parser(
        "commands",
        help="Show the NSX command graph for users and agents",
        description="Show the NSX command tree, arguments, and workflow hints.",
    )
    p_commands.add_argument(
        "--json",
        action="store_true",
        help="Emit the full command graph as machine-readable JSON",
    )
    p_commands.set_defaults(func=cmd_commands)

    p_configure = sub.add_parser("configure", help="Configure a generated NSX app with CMake")
    p_configure.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_configure.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_configure.add_argument("--build-dir", default=None, help="Build directory override")
    p_configure.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    _add_timeout(p_configure)
    p_configure.set_defaults(func=cmd_configure)

    p_build = sub.add_parser("build", help="Build a generated NSX app")
    p_build.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_build.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_build.add_argument("--build-dir", default=None, help="Build directory override")
    p_build.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_build.add_argument("--target", default=None, help="Optional explicit build target")
    p_build.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    _add_timeout(p_build)
    p_build.set_defaults(func=cmd_build)

    p_flash = sub.add_parser("flash", help="Build and flash a generated NSX app")
    p_flash.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_flash.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_flash.add_argument("--build-dir", default=None, help="Build directory override")
    p_flash.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_flash.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    _add_timeout(p_flash)
    p_flash.set_defaults(func=cmd_flash)

    p_view = sub.add_parser("view", help="Open the SEGGER SWO viewer for a generated NSX app")
    p_view.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_view.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_view.add_argument("--build-dir", default=None, help="Build directory override")
    p_view.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_view.add_argument(
        "--no-reset-on-open",
        action="store_true",
        help="Open the SWO viewer without issuing the app reset target after attach",
    )
    p_view.add_argument(
        "--reset-delay-ms",
        type=int,
        default=400,
        help="Milliseconds to wait after opening the SWO viewer before issuing reset",
    )
    _add_timeout(p_view)
    p_view.set_defaults(func=cmd_view)

    p_clean = sub.add_parser("clean", help="Clean a generated NSX app build directory")
    p_clean.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_clean.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_clean.add_argument("--build-dir", default=None, help="Build directory override")
    p_clean.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_clean.add_argument(
        "--full",
        action="store_true",
        help="Remove the full build directory instead of only running the build-system clean target",
    )
    _add_timeout(p_clean)
    p_clean.set_defaults(func=cmd_clean)

    p_lock = sub.add_parser(
        "lock",
        help="Resolve modules in nsx.yml to commits and write nsx.lock",
        description=(
            "Resolve every module declared in nsx.yml to its current upstream commit "
            "and content hash, and write the resulting nsx.lock receipt. Does not "
            "modify the modules/ tree."
        ),
    )
    p_lock.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_lock.add_argument(
        "--update",
        action="store_true",
        help="Re-resolve constraints to current upstream tip (otherwise reuses prior SHAs)",
    )
    p_lock.add_argument(
        "--module",
        dest="modules",
        action="append",
        default=[],
        help="Only re-resolve the named module (may be repeated; implies --update)",
    )
    p_lock.add_argument(
        "--check",
        action="store_true",
        help=("Exit non-zero if nsx.lock is out of date with nsx.yml (do not write); useful in CI"),
    )
    _add_timeout(p_lock)
    p_lock.set_defaults(func=cmd_lock)

    p_sync = sub.add_parser(
        "sync",
        help="Make modules/ exactly match nsx.lock",
        description=(
            "Re-vendor each module from nsx.lock at its locked commit. Idempotent: "
            "modules whose on-disk content already matches the lock are skipped."
        ),
    )
    p_sync.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_sync.add_argument(
        "--frozen",
        action="store_true",
        help="Error on any drift between nsx.yml, nsx.lock, and modules/ instead of correcting it",
    )
    p_sync.add_argument(
        "--force",
        action="store_true",
        help="Re-vendor every module even if its content_hash matches the lock",
    )
    _add_timeout(p_sync)
    p_sync.set_defaults(func=cmd_sync)

    p_outdated = sub.add_parser(
        "outdated",
        help="Show git modules whose locked commit lags behind upstream",
        description=(
            "For each git module in nsx.lock, compare the locked commit "
            "against the current upstream tip of the constraint and report "
            "any drift."
        ),
    )
    p_outdated.add_argument("--app-dir", default=".", help="App directory containing nsx.lock")
    p_outdated.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit non-zero if any modules are outdated (useful in CI)",
    )
    p_outdated.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the human-readable table",
    )
    _add_timeout(p_outdated)
    p_outdated.set_defaults(func=cmd_outdated)

    p_update = sub.add_parser(
        "update",
        help="Re-resolve constraints to upstream tip and sync modules",
        description=(
            "Re-resolve every (or selected) module constraint to its current "
            "upstream tip, rewrite nsx.lock, and re-vendor changed modules. "
            "Equivalent to `nsx lock --update [--module ...] && nsx sync`."
        ),
    )
    p_update.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_update.add_argument(
        "--module",
        dest="modules",
        action="append",
        default=[],
        help="Only update the named module (may be repeated)",
    )
    _add_timeout(p_update)
    p_update.set_defaults(func=cmd_update)

    p_mod = sub.add_parser(
        "module",
        help="Manage app-local NSX modules",
        description="List, enable, update, and register app-local NSX modules.",
    )
    mod_sub = p_mod.add_subparsers(dest="module_command", required=True)

    p_mod_list = mod_sub.add_parser(
        "list",
        help="List modules from the packaged or app-effective registry",
        description=(
            "List modules from the packaged registry, or from the effective registry for an app and mark enabled ones."
        ),
    )
    p_mod_list.add_argument(
        "--app-dir",
        default=None,
        help="App directory containing nsx.yml; required unless --registry-only is used",
    )
    p_mod_list.add_argument(
        "--registry-only",
        action="store_true",
        help="List all modules in the packaged registry without app-specific overrides",
    )
    p_mod_list.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table",
    )
    p_mod_list.set_defaults(func=cmd_module_list)

    p_mod_describe = mod_sub.add_parser(
        "describe",
        help="Show detailed metadata for one module",
        description="Describe one module from the packaged or app-effective registry.",
    )
    p_mod_describe.add_argument("module", help="Module name to describe")
    p_mod_describe.add_argument(
        "--app-dir",
        default=None,
        help="Optional app directory containing nsx.yml; when provided, use the app-effective registry",
    )
    p_mod_describe.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_mod_describe.set_defaults(func=cmd_module_describe)

    p_mod_search = mod_sub.add_parser(
        "search",
        help="Search modules by intent, capability, or keyword",
        description="Search the packaged or app-effective registry using module metadata and optional target-compatibility filters.",
    )
    p_mod_search.add_argument("query", help="Search query such as pmu, profiling, uart, or logging")
    p_mod_search.add_argument(
        "--app-dir",
        default=None,
        help="Optional app directory containing nsx.yml; when provided, use the app-effective registry and app target context",
    )
    p_mod_search.add_argument("--board", default=None, help="Optional board compatibility filter")
    p_mod_search.add_argument("--soc", default=None, help="Optional SoC compatibility filter")
    p_mod_search.add_argument(
        "--toolchain", default=None, help="Optional toolchain compatibility filter"
    )
    p_mod_search.add_argument(
        "--include-incompatible",
        action="store_true",
        help="Include matches that fail the active compatibility filters",
    )
    p_mod_search.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_mod_search.set_defaults(func=cmd_module_search)

    p_mod_add = mod_sub.add_parser(
        "add",
        help="Enable a registry module for an app",
        description="Enable a module for an app and vendor its resolved dependency closure.",
    )
    p_mod_add.add_argument("module", help="Module name to enable")
    p_mod_add.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_add.add_argument(
        "--local",
        action="store_true",
        help="Mark the module as local (mirrored from external path; ignored by git)",
    )
    p_mod_add.add_argument(
        "--vendored",
        action="store_true",
        help=(
            "Scaffold a vendored module under modules/<name>/ "
            "(committed in this app's git; never touched by `nsx sync`)"
        ),
    )
    p_mod_add.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_add.set_defaults(func=cmd_module_add)

    p_mod_remove = mod_sub.add_parser(
        "remove",
        help="Disable a module for an app",
        description="Disable a module for an app and remove vendored files that are no longer needed.",
    )
    p_mod_remove.add_argument("module", help="Module name to remove")
    p_mod_remove.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_remove.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_remove.set_defaults(func=cmd_module_remove)

    p_mod_update = mod_sub.add_parser(
        "update",
        help="Refresh enabled modules to current registry revisions",
        description="Refresh vendored modules for an app using the current active registry revisions.",
    )
    p_mod_update.add_argument(
        "module", nargs="?", default=None, help="Optional single module to refresh"
    )
    p_mod_update.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_update.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mod_update.set_defaults(func=cmd_module_update)

    p_mod_init = mod_sub.add_parser(
        "init",
        help="Create a standard custom-module skeleton",
        description="Scaffold a new NSX custom-module directory with metadata, CMake, headers, and source stubs.",
    )
    p_mod_init.add_argument("module_dir", help="Directory to create for the module skeleton")
    p_mod_init.add_argument(
        "--name",
        default=None,
        help="Logical module name (defaults to the directory name)",
    )
    p_mod_init.add_argument(
        "--type",
        choices=sorted(SUPPORTED_MODULE_TYPES),
        default="runtime",
        help="NSX module type for the generated metadata",
    )
    p_mod_init.add_argument(
        "--summary",
        default=None,
        help="One-line module summary to seed into nsx-module.yaml",
    )
    p_mod_init.add_argument(
        "--version",
        default="0.1.0",
        help="Initial semantic version for the module",
    )
    p_mod_init.add_argument(
        "--dependency",
        action="append",
        default=[],
        help="Required module dependency to add to the skeleton; repeat as needed",
    )
    p_mod_init.add_argument(
        "--board",
        action="append",
        default=[],
        help="Compatible board to declare; repeat as needed (defaults to *)",
    )
    p_mod_init.add_argument(
        "--soc",
        action="append",
        default=[],
        help="Compatible SoC to declare; repeat as needed (defaults to *)",
    )
    p_mod_init.add_argument(
        "--toolchain",
        action="append",
        default=[],
        help="Compatible toolchain to declare; repeat as needed (defaults to arm-none-eabi-gcc)",
    )
    p_mod_init.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty destination directory",
    )
    p_mod_init.set_defaults(func=cmd_module_init)

    p_mod_register = mod_sub.add_parser(
        "register",
        help="Register and vendor an external module for one app",
        description="Register an external module override for a single app and vendor it into that app.",
    )
    p_mod_register.add_argument("module", help="Module name")
    p_mod_register.add_argument(
        "--metadata", required=True, help="Path to the module's nsx-module.yaml"
    )
    p_mod_register.add_argument(
        "--project", required=True, help="Registry project key for this module"
    )
    p_mod_register.add_argument("--project-url", default=None, help="Override git project URL")
    p_mod_register.add_argument(
        "--project-revision", default=None, help="Override git project revision"
    )
    p_mod_register.add_argument("--project-path", default=None, help="Override git project path")
    p_mod_register.add_argument(
        "--project-local-path", default=None, help="Local filesystem path to vendor from"
    )
    p_mod_register.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_mod_register.add_argument(
        "--override", action="store_true", help="Override existing module entry"
    )
    p_mod_register.add_argument(
        "--dry-run", action="store_true", help="Show changes without writing"
    )
    p_mod_register.set_defaults(func=cmd_module_register)

    p_mod_validate = mod_sub.add_parser(
        "validate",
        help="Validate an nsx-module.yaml file",
        description="Check that an nsx-module.yaml file has all required fields and valid values.",
    )
    p_mod_validate.add_argument("metadata", help="Path to the nsx-module.yaml file to validate")
    p_mod_validate.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_mod_validate.set_defaults(func=cmd_module_validate)

    p_cache = sub.add_parser(
        "cache",
        help="Inspect or clean the on-disk module artifact cache",
        description=(
            "Manage the content-addressed cache of vendored module "
            "artifacts under $NSX_CACHE_DIR/modules/. Cache hits let "
            "`nsx sync` skip git clones for already-seen (commit, "
            "content_hash) tuples."
        ),
    )
    cache_sub = p_cache.add_subparsers(dest="cache_command", required=True)

    p_cache_info = cache_sub.add_parser(
        "info",
        help="Show cache location, entry count, and total size",
        description="Show cache location, entry count, and total size on disk.",
    )
    p_cache_info.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_cache_info.set_defaults(func=cmd_cache_info)

    p_cache_clean = cache_sub.add_parser(
        "clean",
        help="Remove every cached module artifact",
        description=(
            "Delete every cache entry. Subsequent `nsx sync` runs will "
            "re-clone modules and repopulate the cache."
        ),
    )
    p_cache_clean.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion (required; without it the command is a dry-run)",
    )
    p_cache_clean.set_defaults(func=cmd_cache_clean)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose, quiet=args.quiet)
    operations.set_verbosity(args.verbose)
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        if args.verbose > 0:
            raise
        sys.stderr.write(f"error: {format_subprocess_error(exc, context='Command')}\n")
        return 1
    except nsx_lock.LegacyLockError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except NSXError as exc:
        # Typed library errors: print message (if any) and exit non-zero.
        msg = str(exc)
        if msg and msg != "1":
            sys.stderr.write(f"error: {msg}\n")
        return 1
    return 0
