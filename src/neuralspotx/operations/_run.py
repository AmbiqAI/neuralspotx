"""Run a previously built Corstone ELF and verify guest completion."""

from __future__ import annotations

import math
import mmap
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .._errors import NSXConfigError, NSXTimeoutError, NSXToolchainError
from ..constants import normalize_board
from ..models import AppConfig, RunResult
from ..project_config import _default_build_dir, _load_app_cfg
from ..subprocess_utils import run
from ._debug_workflow import DebugState, inspect_build


@dataclass(frozen=True)
class _Fvp:
    executable: str
    board_component: str
    settings: tuple[str, ...]


_MODELS = {
    "corstone300_fvp_u55": _Fvp(
        "FVP_Corstone_SSE-300_Ethos-U55",
        "mps3_board",
        (
            "cpu0.CFGDTCMSZ=12",
            "cpu0.CFGITCMSZ=12",
            "ethosu.num_macs=32",
        ),
    ),
    "corstone320_fvp_u85": _Fvp(
        "FVP_Corstone_SSE-320",
        "mps4_board",
        (
            "vis_hdlcd.disable_visualisation=1",
            "mps4_board.subsystem.ethosu.num_macs=256",
        ),
    ),
}
_EXIT_RECORD = re.compile(
    rb"Application exit code: (0|-?[1-9][0-9]{0,9})\.\r?\n\x04(?:\r?\nEXITTHESIM(?:\r?\n)?)?"
)


def _guest_exit_code(uart: Path) -> int:
    """Verify the complete final retarget record (EOT or shutdown-tag form)."""
    if uart.is_file() and uart.stat().st_size:
        with (
            uart.open("rb") as stream,
            mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data,
        ):
            # The retarget appends its record directly to the final UART byte.
            # A complete earlier record would make the transcript ambiguous.
            match = _EXIT_RECORD.search(data)
            if match and match.end() == len(data):
                code = int(match[1])
                if -(2**31) <= code < 2**31:
                    return code
    raise NSXToolchainError(f"Missing, ambiguous or incomplete guest exit record in {uart}")


def run_app_impl(
    app_dir: Path,
    *,
    board: str | None,
    build_dir: Path | None,
    elf: Path | None,
    fvp: Path | None,
    timeout_s: float,
) -> RunResult:
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise NSXConfigError("Model timeout must be positive and finite.")
    project = AppConfig.from_mapping(_load_app_cfg(app_dir))
    selected = normalize_board(project.resolve_target(board).board)
    profile = _MODELS.get(selected)
    if profile is None:
        raise NSXConfigError(
            f"Board '{selected}' has no simulator runner. Select one of {', '.join(_MODELS)}."
        )
    build = (build_dir or _default_build_dir(app_dir, selected)).resolve()
    if inspect_build(app_dir, build, selected).state is DebugState.UNCONFIGURED:
        raise NSXConfigError(
            f"Build directory is not configured for {selected}. Run `nsx build` first."
        )
    image = (build / (elf if elf is not None else project.project_name)).resolve()
    if not image.is_relative_to(build) or not image.is_file():
        raise NSXConfigError(
            f"Expected a built ELF inside {build}. Run `nsx build` or select it with --elf."
        )
    with image.open("rb") as stream:
        header = stream.read(20)
    # ELF32, little endian, executable for Arm.
    if header[:6] != b"\x7fELF\x01\x01" or header[16:20] != b"\x02\x00\x28\x00":
        raise NSXConfigError(f"Expected a 32-bit Arm executable ELF: {image}")
    executable = (
        shutil.which(profile.executable) if fvp is None else str(fvp.expanduser().resolve())
    )
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise NSXConfigError(
            f"Install Arm's {profile.executable} on PATH or pass its executable path with --fvp."
        )
    model = Path(executable).resolve()
    output = build / "nsx-run"
    output.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    uart = work / "uart.log"
    model_log = work / "model.log"
    settings = [
        *profile.settings,
        f"{profile.board_component}.visualisation.disable-visualisation=1",
        *(
            f"{profile.board_component}.telnetterminal{port}.start_telnet=0"
            for port in (0, 1, 2, 5)
        ),
        f"{profile.board_component}.uart0.out_file=uart.log",
        f"{profile.board_component}.uart0.unbuffered_output=1",
        f"{profile.board_component}.uart0.shutdown_on_eot=1",
        f"{profile.board_component}.uart0.shutdown_tag=EXITTHESIM",
    ]
    command = [str(model)]
    for setting in settings:
        command.extend(["-C", setting])
    command.extend(["-a", str(image)])
    with model_log.open("wb") as host_output:
        try:
            run(command, cwd=work, timeout=timeout_s, output=host_output)
        except subprocess.TimeoutExpired as exc:
            raise NSXTimeoutError(
                f"FVP timed out after {timeout_s:g}s. Run logs: {work}",
                command=str(model),
                timeout_s=timeout_s,
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise NSXToolchainError(
                f"FVP process exited with status {exc.returncode}. Run logs: {work}"
            ) from exc
        except (NSXToolchainError, OSError) as exc:
            raise NSXToolchainError(f"Could not launch {model}: {exc}. Run logs: {work}") from exc
    return RunResult(selected, image, model, _guest_exit_code(uart), uart, model_log)
