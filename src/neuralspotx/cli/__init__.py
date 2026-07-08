# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""NSX CLI — create and manage bare-metal Ambiq applications.

Public entry point. The ``cmd_*`` handlers and supporting helpers are
split across sibling modules to keep this file scoped to argparse wiring
and the high-level workflow handlers (create-app / doctor / build /
flash / lock / sync / outdated / update / sbom):

* :mod:`._hints` — shared ``@command_hint`` decorator + registry.
* :mod:`._render` — stateless formatting / JSON / introspection helpers.
* :mod:`._cmd_module` — every ``nsx module …`` handler.
* :mod:`._cmd_cache` — every ``nsx cache …`` handler.

All public names (``main``, every ``cmd_*`` handler) remain importable
from ``neuralspotx.cli`` for backwards compatibility.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .. import api, operations
from .._errors import NSXError, NSXToolchainError
from .._logging import configure_logging
from ..constants import DEFAULT_BOARD
from ..metadata import SUPPORTED_MODULE_TYPES
from ..models import CommandCategory, CommandHint, CommandScope, OutdatedReport
from ..project_config import resolve_app_dir
from ..subprocess_utils import format_subprocess_error
from ..tooling import JLinkProbe, list_jlink_probes
from ._cmd_board import cmd_board_create, cmd_board_list, cmd_board_show
from ._cmd_cache import cmd_cache_clean, cmd_cache_info
from ._cmd_module import (
    cmd_module_add,
    cmd_module_describe,
    cmd_module_init,
    cmd_module_list,
    cmd_module_register,
    cmd_module_remove,
    cmd_module_search,
    cmd_module_update,
    cmd_module_validate,
)
from ._hints import _COMMAND_GRAPH_HINTS, _register_group_hint, command_hint
from ._render import _command_graph, _render_outdated_report

_C = CommandCategory
_S = CommandScope


def _selected_app_dir(args: argparse.Namespace) -> Path:
    """Resolve the target app directory from the positional selector or --app-dir.

    The optional positional ``app`` (a name or path) takes precedence over
    ``--app-dir`` when supplied.
    """

    selector = getattr(args, "app", None) or getattr(args, "app_dir", None)
    return resolve_app_dir(selector)


_register_group_hint("", _C.ENTRYPOINT, _S.GLOBAL, "nsx doctor", "nsx create-app")
_COMMAND_GRAPH_HINTS["new"] = CommandHint(
    _C.APP_CREATION,
    _S.APP,
    ("nsx configure", "nsx module list", "nsx module add"),
    alias_for="nsx create-app",
)
# G2: top-level aliases for the most common module operations.
_COMMAND_GRAPH_HINTS["add"] = CommandHint(
    _C.MODULES,
    _S.APP,
    ("nsx configure", "nsx build", "nsx flash"),
    alias_for="nsx module add",
)
_COMMAND_GRAPH_HINTS["list-modules"] = CommandHint(
    _C.MODULES,
    _S.APP,
    ("nsx module describe <module>", "nsx module add <module>"),
    alias_for="nsx module list",
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
_register_group_hint(
    "board",
    _C.DISCOVERY,
    _S.GLOBAL,
    "nsx board list",
    "nsx board show <board>",
    "nsx board create <name> --from <evb>",
)
_register_group_hint("cache", _C.MAINTENANCE, _S.GLOBAL, "nsx cache info", "nsx cache clean")


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
    if getattr(args, "json", False):
        # Run doctor with a no-op emitter so the diagnostic line output
        # does not pollute the JSON document on stdout.
        report = api.doctor(emit=lambda _event: None)
        print(json.dumps(report.to_dict(), indent=2))
        if not report.ok:
            raise NSXToolchainError("One or more required tools are missing or misconfigured.")
        return
    report = api.doctor()
    if not report.ok:
        # G4: surface a recovery hint before the typed error so the user
        # has a single concrete next command to run.
        print("Next: install or fix the failing tool above, then re-run `nsx doctor`.")
        raise NSXToolchainError("One or more required tools are missing or misconfigured.")
    # G4: success-path next-step suggestion.
    print("Next: nsx create-app my_app")


def _probe_to_dict(probe: JLinkProbe) -> dict[str, object]:
    return {
        "index": probe.index,
        "serial": probe.serial,
        "product": probe.product,
        "nickname": probe.nickname,
    }


@command_hint("probes", _C.DISCOVERY, _S.ENVIRONMENT, "nsx flash --probe-serial <sn>")
def cmd_probes(args: argparse.Namespace) -> None:
    probes = list_jlink_probes()
    if args.json:
        print(json.dumps([_probe_to_dict(probe) for probe in probes], indent=2))
        return
    if not probes:
        print("No J-Link probes found.")
        return
    serial_w = max(len(probe.serial) for probe in probes)
    product_w = max(len(probe.product) for probe in probes)
    print(f"{'SERIAL':<{serial_w}}  {'PRODUCT':<{product_w}}  NICKNAME")
    for probe in probes:
        print(f"{probe.serial:<{serial_w}}  {probe.product:<{product_w}}  {probe.nickname or '-'}")


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
        _selected_app_dir(args),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        probe_serial=getattr(args, "probe_serial", None),
        frozen=getattr(args, "frozen", False),
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("build", _C.BUILD, _S.APP, "nsx flash", "nsx view", "nsx clean")
def cmd_build(args: argparse.Namespace) -> None:
    app_dir = _selected_app_dir(args)
    if getattr(args, "update", False):
        api.update_app(app_dir, timeout_s=getattr(args, "timeout", None))
    api.build_app(
        app_dir,
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        target=args.target,
        jobs=args.jobs,
        frozen=getattr(args, "frozen", False),
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("flash", _C.DEPLOY, _S.APP, "nsx view")
def cmd_flash(args: argparse.Namespace) -> None:
    app_dir = _selected_app_dir(args)
    if getattr(args, "update", False):
        api.update_app(app_dir, timeout_s=getattr(args, "timeout", None))
    api.flash_app(
        app_dir,
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        probe_serial=getattr(args, "probe_serial", None),
        jobs=args.jobs,
        frozen=getattr(args, "frozen", False),
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("view", _C.DEPLOY, _S.APP, "nsx build", "nsx flash")
def cmd_view(args: argparse.Namespace) -> None:
    api.view_app(
        _selected_app_dir(args),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        probe_serial=getattr(args, "probe_serial", None),
        reset_on_open=getattr(args, "reset_on_open", None),
        reset_delay_ms=args.reset_delay_ms,
        duration_s=getattr(args, "duration", None),
        capture=Path(args.capture).expanduser().resolve()
        if getattr(args, "capture", None)
        else None,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("clean", _C.BUILD, _S.APP, "nsx configure", "nsx build")
def cmd_clean(args: argparse.Namespace) -> None:
    api.clean_app(
        _selected_app_dir(args),
        board=args.board,
        build_dir=Path(args.build_dir).expanduser().resolve() if args.build_dir else None,
        toolchain=args.toolchain,
        full=args.full,
        reset=getattr(args, "reset", False),
        force=getattr(args, "force", False),
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
    report: OutdatedReport = api.outdated_app(
        resolve_app_dir(args.app_dir),
        timeout_s=getattr(args, "timeout", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _render_outdated_report(report)
    if args.exit_code and report.outdated_count:
        raise NSXError(1)


_UPDATE_CONFIRM_THRESHOLD = 3


def _confirm_update_changes(report: OutdatedReport, *, assume_yes: bool) -> None:
    """G5 confirmation gate for ``nsx update``.

    Prints a one-line diff summary of what will move and, when at least
    ``_UPDATE_CONFIRM_THRESHOLD`` modules are outdated, requires either
    ``--yes`` or an interactive ``y`` reply on stdin. Raises
    :class:`NSXError` when the user declines or when the gate is hit
    non-interactively without ``--yes``.
    """

    outdated = report.outdated
    if not outdated:
        return

    summary = ", ".join(f"{m.name} ({m.locked[:10]}->{m.upstream[:10]})" for m in outdated)
    print(f"{len(outdated)} module(s) will move: {summary}")

    if assume_yes or len(outdated) < _UPDATE_CONFIRM_THRESHOLD:
        return

    if not sys.stdin.isatty():
        raise NSXError(
            f"`nsx update` will move {len(outdated)} modules; pass --yes to confirm "
            "non-interactively."
        )

    reply = input(f"Proceed updating {len(outdated)} modules? [y/N] ").strip().lower()
    if reply not in ("y", "yes"):
        raise NSXError("Aborted by user.")


@command_hint("update", _C.MODULES, _S.APP, "nsx configure", "nsx build", "nsx flash")
def cmd_update(args: argparse.Namespace) -> None:
    app_dir = resolve_app_dir(args.app_dir)
    # G5: peek upstream so we can show a one-line diff and gate large updates.
    report: OutdatedReport = api.outdated_app(app_dir, timeout_s=getattr(args, "timeout", None))
    _confirm_update_changes(report, assume_yes=bool(getattr(args, "yes", False)))
    api.update_app(
        app_dir,
        modules=list(args.modules) if args.modules else None,
        timeout_s=getattr(args, "timeout", None),
    )


@command_hint("sbom", _C.DISCOVERY, _S.APP, "nsx lock", "nsx sync")
def cmd_sbom(args: argparse.Namespace) -> None:
    document = api.generate_sbom(
        resolve_app_dir(args.app_dir),
        format=args.format,
    )
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(document, encoding="utf-8")
        print(f"Wrote {args.format.upper()} SBOM to {out_path}")
    else:
        print(document)


# G1: tier the top-level command list into logical groups so `nsx --help`
# guides new users from quickstart -> module management -> maintenance.
# Aliases (G2) are listed under their semantic group with the canonical
# command they forward to.
_HELP_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Quickstart",
        (
            ("create-app", "Create a new standalone NSX app project"),
            ("new", "Alias for create-app"),
            ("doctor", "Check the local NSX toolchain environment"),
            ("probes", "List connected SEGGER J-Link debug probes"),
            ("configure", "Configure a generated NSX app with CMake"),
            ("build", "Build a generated NSX app"),
            ("flash", "Build and flash a generated NSX app"),
            ("view", "Open the SEGGER SWO viewer for a generated NSX app"),
        ),
    ),
    (
        "Modules",
        (
            ("add", "Alias for `module add`"),
            ("list-modules", "Alias for `module list`"),
            ("module", "Manage app-local NSX modules (list / describe / search / ...)"),
            ("lock", "Resolve modules in nsx.yml to commits and write nsx.lock"),
            ("sync", "Make modules/ exactly match nsx.lock"),
            ("outdated", "Show git modules whose locked commit lags upstream"),
            ("update", "Re-resolve constraints to upstream tip and sync modules"),
        ),
    ),
    (
        "Maintenance",
        (
            ("clean", "Clean a generated NSX app build directory"),
            ("cache", "Inspect or clean the on-disk module artifact cache"),
        ),
    ),
    (
        "Introspection",
        (
            ("commands", "Show the NSX command graph for users and agents"),
            ("sbom", "Generate a Software Bill of Materials from nsx.lock"),
        ),
    ),
)


def _format_help_groups() -> str:
    lines: list[str] = ["commands (run `nsx <command> --help` for details):", ""]
    for title, entries in _HELP_GROUPS:
        lines.append(f"  {title}:")
        width = max(len(name) for name, _ in entries)
        for name, summary in entries:
            lines.append(f"    {name.ljust(width)}  {summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_TUTORIAL = (
    "NSX is a bare-metal app builder for Ambiq SoCs. Get started:\n"
    "  1) nsx doctor                # check your toolchain environment\n"
    "  2) nsx create-app my_app     # scaffold a new app\n"
    "  3) cd my_app && nsx build    # build it\n"
    "Run `nsx --help` for the full command list.\n"
)


def _maybe_print_tutorial(argv: list[str] | None) -> bool:
    """G3: when invoked bare with no project context, show a 5-line tutorial.

    Returns ``True`` when the tutorial was printed and the caller should
    short-circuit (no parser dispatch).
    """

    effective = argv if argv is not None else sys.argv[1:]
    if effective:
        return False
    if (Path.cwd() / "nsx.yml").exists():
        return False
    config_root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    if (Path(config_root) / "nsx").exists():
        return False
    print(_TUTORIAL, end="")
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NSX helper for creating and building bare-metal Ambiq apps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_format_help_groups(),
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

    def _add_app_selector(p: argparse.ArgumentParser) -> None:
        # Optional positional app selector. When given it overrides
        # ``--app-dir`` and may be either a path or a bare app name that
        # is discovered under ./ or ./examples — so ``nsx build hello_world``
        # works from a repo root holding many app subdirectories.
        p.add_argument(
            "app",
            nargs="?",
            default=None,
            help="App name or directory (overrides --app-dir; resolved under ./ and ./examples)",
        )

    p_new = sub.add_parser("create-app", help="Create a new standalone NSX app project")
    p_new.add_argument("app_dir", help="App directory to create")
    p_new.add_argument("--board", default=DEFAULT_BOARD, help="Target board package suffix")
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
    p_new_alias.add_argument("--board", default=DEFAULT_BOARD, help="Target board package suffix")
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
    p_doctor.add_argument(
        "--json",
        action="store_true",
        help="Emit the full doctor report as machine-readable JSON",
    )
    p_doctor.set_defaults(func=cmd_doctor)

    p_probes = sub.add_parser(
        "probes",
        help="List connected SEGGER J-Link debug probes",
        description="Enumerate connected J-Link probes and print their USB serial numbers.",
    )
    p_probes.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_probes.set_defaults(func=cmd_probes)

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
    _add_app_selector(p_configure)
    p_configure.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_configure.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_configure.add_argument("--build-dir", default=None, help="Build directory override")
    p_configure.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_configure.add_argument(
        "--probe-serial",
        default=None,
        help="Optional SEGGER J-Link USB serial number to use for generated flash/view targets",
    )
    p_configure.add_argument(
        "--frozen",
        action="store_true",
        help="Error on any drift between nsx.yml, nsx.lock, and modules/ instead of correcting it",
    )
    _add_timeout(p_configure)
    p_configure.set_defaults(func=cmd_configure)

    p_build = sub.add_parser("build", help="Build a generated NSX app")
    _add_app_selector(p_build)
    p_build.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_build.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_build.add_argument("--build-dir", default=None, help="Build directory override")
    p_build.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_build.add_argument("--target", default=None, help="Optional explicit build target")
    p_build.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_build.add_argument(
        "--update",
        action="store_true",
        help="Re-resolve module constraints to upstream tip and re-vendor before building",
    )
    p_build.add_argument(
        "--frozen",
        action="store_true",
        help=(
            "When a (re)configure is needed (no build.ninja yet), error on any "
            "drift between nsx.yml, nsx.lock, and modules/ instead of correcting it"
        ),
    )
    _add_timeout(p_build)
    p_build.set_defaults(func=cmd_build)

    p_flash = sub.add_parser("flash", help="Build and flash a generated NSX app")
    _add_app_selector(p_flash)
    p_flash.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_flash.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_flash.add_argument("--build-dir", default=None, help="Build directory override")
    p_flash.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_flash.add_argument(
        "--probe-serial",
        default=None,
        help="Optional SEGGER J-Link USB serial number to use",
    )
    p_flash.add_argument("--jobs", type=int, default=8, help="Parallel build jobs")
    p_flash.add_argument(
        "--update",
        action="store_true",
        help="Re-resolve module constraints to upstream tip and re-vendor before flashing",
    )
    p_flash.add_argument(
        "--frozen",
        action="store_true",
        help=(
            "When a (re)configure is needed, error on any drift between nsx.yml, "
            "nsx.lock, and modules/ instead of correcting it. Note: passing "
            "--probe-serial always forces a reconfigure; --frozen only changes "
            "how the accompanying module sync behaves, not whether it runs."
        ),
    )
    _add_timeout(p_flash)
    p_flash.set_defaults(func=cmd_flash)

    p_view = sub.add_parser("view", help="Open the SEGGER SWO viewer for a generated NSX app")
    _add_app_selector(p_view)
    p_view.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_view.add_argument("--board", default=None, help="Override board from nsx.yml")
    p_view.add_argument("--build-dir", default=None, help="Build directory override")
    p_view.add_argument(
        "--toolchain", default=None, help="Toolchain override (gcc, armclang, atfe)"
    )
    p_view.add_argument(
        "--probe-serial",
        default=None,
        help="Optional SEGGER J-Link USB serial number to use",
    )
    reset_group = p_view.add_mutually_exclusive_group()
    reset_group.add_argument(
        "--reset-on-open",
        dest="reset_on_open",
        action="store_true",
        default=None,
        help="Force a target reset after opening the SWO viewer",
    )
    reset_group.add_argument(
        "--no-reset-on-open",
        dest="reset_on_open",
        action="store_false",
        help="Open the SWO viewer without issuing the app reset target after attach",
    )
    p_view.add_argument(
        "--reset-delay-ms",
        type=int,
        default=400,
        help="Milliseconds to wait after opening the SWO viewer before issuing reset",
    )
    p_view.add_argument(
        "--duration",
        type=float,
        default=None,
        metavar="SECONDS",
        help="Stop the viewer after SECONDS instead of running until interrupted",
    )
    p_view.add_argument(
        "--capture",
        default=None,
        metavar="FILE",
        help="Line-stream the SWO output to FILE in addition to stdout",
    )
    _add_timeout(p_view)
    p_view.set_defaults(func=cmd_view)

    p_clean = sub.add_parser("clean", help="Clean a generated NSX app build directory")
    _add_app_selector(p_clean)
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
    p_clean.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Reset the app to a freshly-cloned state: remove all build*/ directories, "
            "the synced modules/ tree, and the .nsx/ folder. Use this before `git pull` "
            "to force `nsx configure` to re-sync from scratch."
        ),
    )
    p_clean.add_argument(
        "--force",
        action="store_true",
        help="With --reset, discard locally-modified files under modules/ without prompting",
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
    p_update.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Confirm large updates non-interactively. Required when "
            f"{_UPDATE_CONFIRM_THRESHOLD}+ modules will move and stdin is not a tty."
        ),
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
        help="Add a direct dependency to an app",
        description=(
            "Add a module to an app's direct dependencies (modules:). The full "
            "closure is recomputed from the board profile + direct deps at lock time."
        ),
    )
    p_mod_add.add_argument("module", help="Module name to add")
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
    p_mod_add.add_argument(
        "--path",
        metavar="DIR",
        help="Use an external linked checkout at DIR (source: { path: DIR })",
    )
    p_mod_add.add_argument(
        "--board",
        action="append",
        metavar="BOARD",
        help="Scope the dependency to BOARD (repeatable; subset of supported targets)",
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

    p_board = sub.add_parser(
        "board",
        help="Inspect packaged boards and scaffold custom boards",
        description=(
            "List and describe packaged board descriptors, or scaffold a "
            "custom board that inherits an EVB baseline."
        ),
    )
    board_sub = p_board.add_subparsers(dest="board_command", required=True)

    p_board_list = board_sub.add_parser(
        "list",
        help="List available boards",
        description="List packaged board descriptors and their derived SoC/provider facts.",
    )
    p_board_list.add_argument(
        "--tier",
        default=None,
        help="Filter by board tier (e.g. 'evb', 'custom')",
    )
    p_board_list.add_argument(
        "--registered-only",
        action="store_true",
        help="Only show boards registered in the packaged build table",
    )
    p_board_list.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_board_list.set_defaults(func=cmd_board_list)

    p_board_show = board_sub.add_parser(
        "show",
        help="Show details for a single board",
        description="Print the derived facts for one board descriptor.",
    )
    p_board_show.add_argument("board", help="Board name (e.g. apollo510_evb)")
    p_board_show.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_board_show.set_defaults(func=cmd_board_show)

    p_board_create = board_sub.add_parser(
        "create",
        help="Scaffold a custom board that inherits an EVB",
        description=(
            "Create a custom board under <app>/boards/<name>/ that inherits an "
            "existing EVB descriptor. Generates board.yaml and a thin board.cmake."
        ),
    )
    p_board_create.add_argument("name", help="Name for the new custom board")
    p_board_create.add_argument(
        "--from",
        dest="from_board",
        required=True,
        metavar="BOARD",
        help="Parent EVB to inherit from (e.g. apollo510_evb)",
    )
    p_board_create.add_argument(
        "--app-dir",
        dest="app_dir",
        default=None,
        help="Application directory (defaults to the nearest app root)",
    )
    p_board_create.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing board directory",
    )
    p_board_create.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    p_board_create.set_defaults(func=cmd_board_create)

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

    p_sbom = sub.add_parser(
        "sbom",
        help="Generate a Software Bill of Materials from nsx.lock",
        description=(
            "Read nsx.lock and emit a single-document SBOM describing "
            "every vendored module by upstream URL, commit SHA, and "
            "content hash."
        ),
    )
    p_sbom.add_argument("--app-dir", default=".", help="App directory containing nsx.lock")
    p_sbom.add_argument(
        "--format",
        choices=("spdx", "cyclonedx"),
        default="spdx",
        help="SBOM format (default: spdx — SPDX 2.3 JSON)",
    )
    p_sbom.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="FILE",
        help="Write SBOM to FILE instead of stdout",
    )
    p_sbom.set_defaults(func=cmd_sbom)

    # G2: top-level aliases for the most common module operations. They
    # share defaults with the corresponding `module` subcommand so the
    # behaviour is identical end-to-end.
    p_add_alias = sub.add_parser(
        "add",
        help="Alias for `nsx module add`",
        description=(
            "Add a module to an app's direct dependencies (modules:). The full "
            "closure is recomputed from the board profile + direct deps at lock time."
        ),
    )
    p_add_alias.add_argument("module", help="Module name to add")
    p_add_alias.add_argument("--app-dir", default=".", help="App directory containing nsx.yml")
    p_add_alias.add_argument(
        "--local",
        action="store_true",
        help="Mark the module as local (mirrored from external path; ignored by git)",
    )
    p_add_alias.add_argument(
        "--vendored",
        action="store_true",
        help=(
            "Scaffold a vendored module under modules/<name>/ "
            "(committed in this app's git; never touched by `nsx sync`)"
        ),
    )
    p_add_alias.add_argument(
        "--path",
        metavar="DIR",
        help="Use an external linked checkout at DIR (source: { path: DIR })",
    )
    p_add_alias.add_argument(
        "--board",
        action="append",
        metavar="BOARD",
        help="Scope the dependency to BOARD (repeatable; subset of supported targets)",
    )
    p_add_alias.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_add_alias.set_defaults(func=cmd_module_add)

    p_list_alias = sub.add_parser(
        "list-modules",
        help="Alias for `nsx module list`",
        description=(
            "List modules from the packaged registry, or from the effective registry "
            "for an app and mark enabled ones."
        ),
    )
    p_list_alias.add_argument(
        "--app-dir",
        default=None,
        help="App directory containing nsx.yml; required unless --registry-only is used",
    )
    p_list_alias.add_argument(
        "--registry-only",
        action="store_true",
        help="List all modules in the packaged registry without app-specific overrides",
    )
    p_list_alias.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table",
    )
    p_list_alias.set_defaults(func=cmd_module_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    if _maybe_print_tutorial(argv):
        return 0
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
    except NSXError as exc:
        # Typed library errors: print message (if any) and exit non-zero.
        msg = str(exc)
        if msg and msg != "1":
            sys.stderr.write(f"error: {msg}\n")
        return 1
    except OSError as exc:
        # Backstop for environmental failures (permission denied, missing
        # files/dirs, disk full, etc.) that escaped the typed-error
        # boundary in a handler. Re-raise under --verbose for a full
        # traceback; otherwise honour the friendly-failure rule rather
        # than dumping a raw Python traceback on the user.
        if args.verbose > 0:
            raise
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0
