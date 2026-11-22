"""Present the guest UART and distinguish firmware failure from launch failure."""

import argparse
import shutil
import sys

from .. import api
from ..models import CommandCategory, CommandScope
from ..project_config import resolve_app_dir
from ._hints import command_hint


@command_hint("run", CommandCategory.DEPLOY, CommandScope.APP, "nsx build")
def cmd_run(args: argparse.Namespace) -> int:
    try:
        request = api.AppRunRequest(
            app_dir=resolve_app_dir(args.app or args.app_dir),
            board=args.board,
            build_dir=args.build_dir,
            elf=args.elf,
            fvp=args.fvp,
            timeout_s=args.timeout,
        )
        result = api.run_app(request)
        with result.uart_log.open("rb") as uart:
            shutil.copyfileobj(uart, sys.stdout.buffer)
    except (api.NSXError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"Guest exit {result.guest_exit_code}. Run logs: {result.uart_log.parent}", file=sys.stderr
    )
    return int(result.guest_exit_code != 0)
