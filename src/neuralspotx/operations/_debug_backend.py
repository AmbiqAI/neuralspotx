"""Internal dispatch for physical board operations. Selecting a tool never opens a probe."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeVar

from .._errors import NSXConfigError
from .._probe_selection import ProbeRequest as ProbeRequest
from ..models import FlashResult, ResetResult
from ..models._rtt import RttResult, RttSettings
from ._debug_workflow import OwnedBuild, require_physical_debug


@dataclass(frozen=True, slots=True)
class DebugBuild:
    app: Path
    board: str
    build: Path
    target: str


@dataclass(frozen=True, slots=True)
class FlashImage:
    target: str
    artifact: Path  # Producer path reported to the caller.
    captured: Path  # Stable input consumed within the capture scope.
    load_address: int


LineCallback = Callable[[str], None]
Program = Callable[[FlashImage, ProbeRequest, LineCallback | None], FlashResult]


@dataclass(frozen=True, slots=True)
class PreparedFlash:
    image: FlashImage
    program: Program


class FlashDriver(Protocol):
    def preflight(self, probe: ProbeRequest, owned: OwnedBuild) -> None: ...

    def prepare(self, target: DebugBuild) -> bool:
        """Prepare tool inputs; return whether the final generation needs a rebuild."""
        ...

    def capture(self, target: DebugBuild) -> AbstractContextManager[PreparedFlash]: ...


@dataclass(frozen=True, slots=True)
class SwoOptions:
    toolchain: str | None
    sdk_root: Path | None
    frozen: bool
    reset_on_open: bool | None
    reset_delay_ms: int
    duration_s: float | None
    capture: Path | None


ResetKind = Literal["debug", "swpoi"]
Reset = Callable[[DebugBuild, ProbeRequest, ResetKind, str, int | None, bool], ResetResult]
View = Callable[[DebugBuild, ProbeRequest, SwoOptions], Path]


@dataclass(frozen=True, slots=True)
class RttDriver:
    resolve: Callable[[DebugBuild, ProbeRequest], RttSettings]
    capture: Callable[
        [RttSettings, ProbeRequest, float, float, Path | None, Callable[[bytes], None] | None],
        RttResult,
    ]


@dataclass(frozen=True, slots=True)
class DebugBackend:
    name: str
    flash: FlashDriver | None = None
    reset: Reset | None = None
    swo: View | None = None
    rtt: RttDriver | None = None


_T = TypeVar("_T")


def require(operation: _T | None, name: str, board: str, backend: DebugBackend) -> _T:
    if operation is None:
        raise NSXConfigError(f"{name} unavailable for board '{board}' with {backend.name}.")
    return operation


def for_board(app: Path, board: str) -> DebugBackend:
    require_physical_debug(app, board)
    # The shipped configured-target protocol supports J-Link over SWD.
    # Keep imports local: these operation implementations use this dispatch layer.
    from ._build import _jlink_view
    from ._jlink_flash import JLinkFlash
    from ._reset import _jlink_reset
    from ._rtt import _capture_jlink_rtt, _resolve_jlink_rtt

    return DebugBackend(
        name="J-Link",
        flash=JLinkFlash(),
        reset=_jlink_reset,
        swo=_jlink_view,
        rtt=RttDriver(_resolve_jlink_rtt, _capture_jlink_rtt),
    )
