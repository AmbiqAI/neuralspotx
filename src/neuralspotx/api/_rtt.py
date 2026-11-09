"""Library entry points for offline RTT resolution and bounded capture."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import operations
from ..models._rtt import RttResult, RttSettings
from ._requests import AppRttRequest


def resolve_rtt_app(request: AppRttRequest) -> RttSettings:
    """Resolve exact executable, RTT address and debug settings without hardware.

    Requires configuration with this NSX version and a built executable. An
    unset serial remains None; capture requires exactly one connected probe
    unless a serial is supplied explicitly or recorded by CMake.
    """
    return operations.resolve_rtt_app_impl(
        Path(request.app_dir).expanduser().resolve(),
        board=request.board,
        build_dir=Path(request.build_dir).expanduser().resolve() if request.build_dir else None,
        target=request.target,
        probe_serial=request.probe_serial,
    )


def rtt_app(
    request: AppRttRequest,
    *,
    on_data: Callable[[bytes], None] | None = None,
) -> RttResult:
    """Capture channel 0 without resetting or flashing the running target.

    ``on_data`` receives raw bytes synchronously and must return promptly.
    Its exceptions propagate after worker cleanup. ``capture`` creates a new
    binary file exclusively; existing files are never truncated. Partial
    output is retained on failure. Without a callback or file, data is drained
    and counted. The ELF must match the flashed firmware; NSX cannot verify
    this from host artifacts. See :class:`AppRttRequest` for timing bounds.
    """
    settings = resolve_rtt_app(request)
    return operations.rtt_app_impl(
        settings,
        duration_s=request.duration_s,
        startup_timeout_s=request.startup_timeout_s,
        capture=Path(request.capture) if request.capture is not None else None,
        on_data=on_data,
    )
