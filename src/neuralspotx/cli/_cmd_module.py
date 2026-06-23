"""``nsx module …`` subcommand handlers.

Extracted from ``cli.py``. Each handler still uses the
``@command_hint`` decorator from :mod:`._hints`, so importing this
module is enough to keep the discovery graph populated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import api
from .._errors import NSXConfigError, NSXModuleError
from ..metadata import load_yaml, validate_nsx_module_metadata
from ..models import CommandCategory, CommandScope
from ..module_discovery import resolve_module_context, resolve_target_context
from ..module_registry import _print_module_table
from ..project_config import resolve_app_dir
from ._hints import command_hint
from ._render import (
    _print_module_detail,
    _print_module_search_results,
    _render_module_changes,
    _render_module_init,
    _resolve_cli_app_dir,
)

_C = CommandCategory
_S = CommandScope


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
        path=getattr(args, "path", None),
        boards=tuple(getattr(args, "board", None) or ()),
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
