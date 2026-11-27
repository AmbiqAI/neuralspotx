"""J-Link implementation of the configured flash operation (CMake protocol v1)."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .._errors import NSXConfigError, NSXError
from .._io import info, line
from .._probe_selection import ProbeSelection, validate_probe_request
from ..models import FlashResult
from ..subprocess_utils import format_subprocess_error, run, run_capture
from . import _common
from ._debug_backend import DebugBuild, FlashImage, LineCallback, PreparedFlash, ProbeRequest
from ._debug_context import capture_debug_context
from ._debug_workflow import OwnedBuild, prepare_debug, require_adoption
from ._hardware import _jlink_command, flash_programming_verified, validate_flash_paths


class JLinkFlash:
    def validate_probe(self, probe: ProbeRequest) -> None:
        validate_probe_request(probe.identity, probe.discover)

    def preflight(self, target: DebugBuild, owned: OwnedBuild) -> None:
        try:
            require_adoption(owned)
        except NSXConfigError as exc:
            raise NSXConfigError(f"Flash unavailable for board '{target.board}'. {exc}") from exc
        if owned.context is not None:
            owned.context.target(target.target).require("flash")

    def prepare(self, target: DebugBuild) -> bool:
        prepare_debug(target.app, target.build, target.board, required=True)
        # Build preparation may have reconfigured after linking; qualify the final generation.
        return True

    @contextmanager
    def capture(self, target: DebugBuild) -> Iterator[PreparedFlash]:
        with capture_debug_context(
            target.app, target.build, target.board, operation="flash", target=target.target
        ) as snap:
            settings = snap.context.target(target.target)
            binary, recipe = validate_flash_paths(
                snap.directory / "firmware.bin", snap.directory / "flash_cmds.jlink", target.target
            )
            assert settings.load_address is not None and settings.speed_khz is not None
            image = FlashImage(target.target, settings.binary, binary, settings.load_address)

            def program(
                image: FlashImage, probe: ProbeRequest, on_line: LineCallback | None
            ) -> FlashResult:
                serial = ProbeSelection.from_request(
                    probe.identity, probe.discover, settings.configured_serial
                ).resolve()
                assert settings.speed_khz is not None
                cmd = _jlink_command(
                    device=settings.device,
                    interface="SWD",
                    speed_khz=settings.speed_khz,
                    probe_serial=serial,
                    command_file=recipe,
                )
                return _execute_flash(
                    cmd, image.target, image.artifact, settings.flash_recipe, serial, on_line
                )

            yield PreparedFlash(image, program)


def _execute_flash(
    flash_cmd: list[str],
    resolved_target: str,
    artifact: Path,
    recipe: Path,
    probe_serial: str,
    on_line: Callable[[str], None] | None,
) -> FlashResult:
    captured_lines: list[str] = []

    def _capture_line(output_line: str) -> None:
        captured_lines.append(output_line)
        if on_line is not None:
            on_line(output_line)

    if _common.get_verbosity() > 0 or on_line is not None:
        try:
            run(flash_cmd, on_line=_capture_line)
        except subprocess.CalledProcessError as exc:
            raise NSXError(format_subprocess_error(exc, context="Flash")) from None
        output = "\n".join(captured_lines)
    else:
        try:
            result = run_capture(flash_cmd)
        except subprocess.CalledProcessError as exc:
            raise NSXError(format_subprocess_error(exc, context="Flash")) from None
        if result.stdout:
            line(result.stdout.rstrip())
        if result.stderr:
            info(result.stderr.rstrip())
        output = (result.stdout or "") + "\n" + (result.stderr or "")

    if not flash_programming_verified(output):
        raise NSXError(
            f"J-Link exited successfully for target '{resolved_target}' but printed no "
            "recognized flash result: neither a 'Flash download: Total' summary nor a "
            "'Skipped. Contents already match' notice. The device was most likely "
            "programmed; this usually means the installed J-Link Commander words its "
            "summary differently. Inspect the echoed J-Link output for what actually happened."
        )
    return FlashResult(
        target=resolved_target,
        artifact=artifact,
        recipe=recipe,
        probe_serial=probe_serial,
        programming_verified=True,
    )
