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
        binary_output = getattr(sys.stdout, "buffer", None)
        if binary_output is None:
            with result.uart_log.open(encoding="utf-8", errors="replace", newline="") as text:
                shutil.copyfileobj(text, sys.stdout)
        else:
            with result.uart_log.open("rb") as uart:
                shutil.copyfileobj(uart, binary_output)
    except (api.NSXError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        f"Guest exit {result.guest_exit_code}. Run logs: {result.uart_log.parent}", file=sys.stderr
    )
    return int(result.guest_exit_code != 0)
