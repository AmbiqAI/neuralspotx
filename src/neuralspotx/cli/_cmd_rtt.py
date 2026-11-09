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

    def write_text(text: str) -> None:
        # UTF-8 decoding replacement alone is insufficient for redirected
        # cp1252/ASCII stdout: even U+FFFD may be unencodable there.
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(encoding, errors="replace").decode(encoding))
        sys.stdout.flush()

    def output(data: bytes) -> None:
        write_text(decoder.decode(data))

    try:
        result = api.rtt_app(request, on_data=output)
    finally:
        write_text(decoder.decode(b"", final=True))
    print(
        f"RTT: {result.bytes_received} bytes from probe {result.settings.probe_serial}.",
        file=sys.stderr,
    )
    if result.bytes_received == 0:
        print(
            "RTT channel was ready but silent; this does not verify firmware output.",
            file=sys.stderr,
        )
