"""Public entry point for running an app in an Arm FVP."""

from pathlib import Path

from .. import operations
from ..models import RunResult
from ._requests import AppRunRequest


def run_app(request: AppRunRequest) -> RunResult:
    """Launch the built guest and return its signed firmware exit code and log paths.

    The model's own exit status is checked separately. A timeout raises
    NSXTimeoutError. Model failure or missing completion evidence raises
    NSXToolchainError. Diagnostics name the directory containing partial logs.
    """
    return operations.run_app_impl(
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser() if request.build_dir else None,
        elf=Path(request.elf).expanduser() if request.elf else None,
        fvp=Path(request.fvp) if request.fvp else None,
        timeout_s=request.timeout_s,
    )
