"""``nsx board …`` subcommand handlers.

Boards are first-class in NSX: every packaged EVB ships a declarative
``board.yaml`` descriptor (see :mod:`neuralspotx.board_descriptors`).
These handlers expose the descriptor catalog (``list`` / ``show``) and
scaffold custom boards that inherit an EVB baseline (``create``).
"""

from __future__ import annotations

import argparse
import json

from .. import api
from .. import board_descriptors as bd
from .._errors import NSXConfigError
from ..models import CommandCategory, CommandScope
from ._hints import command_hint

_C = CommandCategory
_S = CommandScope


def _descriptor_to_dict(desc: bd.BoardDescriptor) -> dict[str, object]:
    return {
        "name": desc.name,
        "tier": desc.tier,
        "soc": desc.soc,
        "sdk_provider": desc.sdk_provider,
        "registered": desc.registered,
        "cpu": {
            "core": desc.cpu.core,
            "float_abi": desc.cpu.float_abi,
            "abi": desc.cpu.abi,
        },
        "toolchains": list(desc.toolchains),
    }


@command_hint(
    "board list",
    _C.DISCOVERY,
    _S.GLOBAL,
    "nsx board show <board>",
    "nsx board create <name> --from <evb>",
)
def cmd_board_list(args: argparse.Namespace) -> None:
    boards = bd.list_boards(
        tier=args.tier,
        registered_only=args.registered_only,
    )
    boards = sorted(boards, key=lambda b: b.name)
    if args.json:
        print(json.dumps([_descriptor_to_dict(b) for b in boards], indent=2))
        return
    if not boards:
        print("No boards found.")
        return
    name_w = max(len(b.name) for b in boards)
    soc_w = max(len(b.soc) for b in boards)
    print(f"{'BOARD':<{name_w}}  {'SOC':<{soc_w}}  {'TIER':<7}  PROVIDER")
    for b in boards:
        print(f"{b.name:<{name_w}}  {b.soc:<{soc_w}}  {b.tier:<7}  {b.sdk_provider}")


@command_hint(
    "board show",
    _C.DISCOVERY,
    _S.GLOBAL,
    "nsx board list",
    "nsx board create <name> --from <evb>",
)
def cmd_board_show(args: argparse.Namespace) -> None:
    desc = bd.load_board(args.board)
    if desc is None:
        raise NSXConfigError(
            f"unknown board '{args.board}' "
            f"(run `nsx board list` to see available boards)"
        )
    if args.json:
        print(json.dumps(_descriptor_to_dict(desc), indent=2))
        return
    print(f"board:        {desc.name}")
    print(f"tier:         {desc.tier}")
    print(f"soc:          {desc.soc}")
    print(f"sdk_provider: {desc.sdk_provider}")
    print(f"registered:   {desc.registered}")
    print(f"cpu:          {desc.cpu.core} ({desc.cpu.abi}, float={desc.cpu.float_abi})")
    print(f"toolchains:   {', '.join(desc.toolchains)}")


@command_hint(
    "board create",
    _C.APP_CREATION,
    _S.FILESYSTEM,
    "nsx board show <name>",
    "nsx configure",
)
def cmd_board_create(args: argparse.Namespace) -> None:
    if args.json:
        # Suppress progress/next-step chatter; emit only the JSON document.
        resolved = api.create_board(
            args.name,
            from_board=args.from_board,
            app_dir=args.app_dir,
            force=args.force,
            emit=lambda _event: None,
        )
        print(json.dumps(_descriptor_to_dict(resolved), indent=2))
        return
    api.create_board(
        args.name,
        from_board=args.from_board,
        app_dir=args.app_dir,
        force=args.force,
    )
