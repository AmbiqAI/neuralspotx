"""``nsx cache …`` subcommand handlers."""

from __future__ import annotations

import argparse
import json

from .. import api
from ..models import CommandCategory, CommandScope
from ._hints import command_hint
from ._render import _format_bytes

_C = CommandCategory
_S = CommandScope


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
