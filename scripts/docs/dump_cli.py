# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Dump the ``nsx`` argparse tree to JSON for the generated CLI reference.

The reference has to describe what the CLI actually parses, so this walks the
parser object built by ``neuralspotx.cli._build_parser`` rather than reading
the source. Every command, subcommand, positional, option, default, choice and
help string ends up in the JSON, and ``tests/test_reference_generation.py``
asserts the rendered pages cover all of it.

Aliases are registered as ordinary sibling parsers rather than through
argparse's ``aliases=``, so they cannot be recovered from the tree. ``ALIASES``
names them and the test asserts each one still dispatches to the same handler
as its target.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from neuralspotx.cli import _build_parser

# Alias command -> the command it stands in for. Verified against the parser's
# ``func`` default so a divergence fails the test rather than the docs.
ALIASES = {
    "new": "create-app",
    "add": "module add",
    "list-modules": "module list",
}


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _format_default(action: argparse.Action) -> str | None:
    """The default worth showing a reader, or None when there is none.

    ``--no-x`` stores False and therefore carries an argparse default of True.
    That True is the value of the *other* flag in the pair, not a default for
    this one, so showing it would tell the reader the opposite of the truth.
    """
    if isinstance(action, argparse._StoreFalseAction):
        return None
    value = action.default
    if value is None or value is False or isinstance(value, argparse.Namespace):
        return None
    if value is True:
        return "true"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or None
    return str(value)


def _exclusive_groups(parser: argparse.ArgumentParser) -> dict[str, list[str]]:
    """Map each option to the flags it is mutually exclusive with."""
    paired: dict[str, list[str]] = {}
    for group in parser._mutually_exclusive_groups:
        flags = [a.option_strings[-1] for a in group._group_actions if a.option_strings]
        for flag in flags:
            paired[flag] = [other for other in flags if other != flag]
    return paired


def _argument(action: argparse.Action, exclusive: dict[str, list[str]]) -> dict[str, Any] | None:
    if isinstance(action, argparse._SubParsersAction):
        return None
    if isinstance(action, argparse._HelpAction):
        return None
    positional = not action.option_strings
    name = action.dest if positional else action.option_strings[-1]
    # A positional with nargs '?' or '*' may be omitted, so it is not required
    # however much argparse's own `required` attribute says about positionals.
    optional_positional = action.nargs in {"?", "*"}
    return {
        "name": name,
        "flags": list(action.option_strings),
        "positional": positional,
        "metavar": action.metavar,
        "nargs": action.nargs if action.nargs is None else str(action.nargs),
        "required": (not optional_positional) if positional else bool(action.required),
        "repeatable": action.__class__.__name__ in {"_AppendAction", "_CountAction"}
        or action.nargs in {"*", "+"},
        "takes_value": not isinstance(
            action, (argparse._StoreTrueAction, argparse._StoreFalseAction, argparse._CountAction)
        ),
        "default": _format_default(action),
        "choices": [str(choice) for choice in action.choices] if action.choices else None,
        "exclusive_with": exclusive.get(name) or None,
        "help": (action.help or "").strip() or None,
    }


def _arguments(parser: argparse.ArgumentParser) -> list[dict[str, Any]]:
    exclusive = _exclusive_groups(parser)
    return [a for a in (_argument(x, exclusive) for x in parser._actions) if a is not None]


def _usage(parser: argparse.ArgumentParser, path: list[str]) -> str:
    parser.prog = " ".join(["nsx", *path])
    return parser.format_usage().replace("usage: ", "", 1).strip()


def _walk(parser: argparse.ArgumentParser, path: list[str]) -> dict[str, Any]:
    name = " ".join(path)
    node: dict[str, Any] = {
        "name": name,
        "path": path,
        "slug": "-".join(path),
        "help": (getattr(parser, "_docs_help", None) or "").strip() or None,
        "description": (parser.description or "").strip() or None,
        "usage": _usage(parser, path),
        "arguments": _arguments(parser),
        "alias_of": ALIASES.get(name),
        "subcommands": [],
    }
    action = _subparsers_action(parser)
    if action is not None:
        for choice, subparser in action.choices.items():
            child = _walk(subparser, [*path, choice])
            child["help"] = next(
                (c.help for c in action._choices_actions if c.dest == choice), child["help"]
            )
            node["subcommands"].append(child)
        node["subcommands"].sort(key=lambda item: item["name"])
    return node


def build() -> dict[str, Any]:
    parser = _build_parser()
    action = _subparsers_action(parser)
    if action is None:
        raise SystemExit("dump_cli: the nsx parser has no subcommands")

    helps = {c.dest: c.help for c in action._choices_actions}
    commands = []
    for choice, subparser in action.choices.items():
        node = _walk(subparser, [choice])
        node["help"] = (helps.get(choice) or node["help"] or "").strip() or None
        commands.append(node)
    commands.sort(key=lambda item: item["name"])

    return {
        "program": "nsx",
        "description": (parser.description or "").strip(),
        "usage": _usage(parser, []),
        "global_arguments": _arguments(parser),
        "aliases": dict(sorted(ALIASES.items())),
        "commands": commands,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, help="write the JSON here instead of stdout")
    args = parser.parse_args(argv)

    payload = json.dumps(build(), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
