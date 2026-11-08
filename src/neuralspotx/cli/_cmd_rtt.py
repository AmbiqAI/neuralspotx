"""RTT presentation; capture and resolution belong to the shared API."""

from __future__ import annotations

import argparse
import codecs
import json
import sys
from dataclasses import asdict

from .. import api
from ..models import CommandCategory, CommandScope
from ..project_config import resolve_app_dir
from ._hints import command_hint


@command_hint("rtt", CommandCategory.DEPLOY, CommandScope.APP, "nsx build", "nsx flash")
def cmd_rtt(args: argparse.Namespace) -> None:
    request = api.AppRttRequest(
        app_dir=resolve_app_dir(args.app or args.app_dir),
        board=args.board,
        build_dir=args.build_dir,
        target=args.target,
        probe_serial=args.probe_serial,
        duration_s=args.duration,
        startup_timeout_s=args.startup_timeout,
        capture=args.capture,
    )
    if args.print_settings:
        print(json.dumps(asdict(api.resolve_rtt_app(request)), default=str, indent=2))
        return
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def output(data: bytes) -> None:
        sys.stdout.write(decoder.decode(data))
        sys.stdout.flush()

    try:
        result = api.rtt_app(request, on_data=output)
    finally:
        sys.stdout.write(decoder.decode(b"", final=True))
        sys.stdout.flush()
    print(
        f"RTT: {result.bytes_received} bytes from probe {result.settings.probe_serial}.",
        file=sys.stderr,
    )
    if result.bytes_received == 0:
        print(
            "RTT channel was ready but silent; this does not verify firmware output.",
            file=sys.stderr,
        )
