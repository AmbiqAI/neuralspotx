"""Shared NSX constants used by the CLI and library operations."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from .board_descriptors import BoardDescriptorError, load_board_descriptors

if TYPE_CHECKING:
    from collections.abc import Iterable

# Canonical ordering of *registered* boards. This is the single place that
# governs which boards appear in the legacy ``DEFAULT_SOC_FOR_BOARD`` /
# ``BOARD_SDK_PROVIDER`` tables and in what order (the order is load-bearing
# for the generated ``nsx_board_table.cmake``). The per-board *values* are
# derived from the ``board.yaml`` descriptors — see
# :mod:`neuralspotx.board_descriptors`. A board ships a descriptor with
# ``registered: false`` to remain out of these tables.
_BOARD_ORDER: tuple[str, ...] = (
    "apollo2_evb",
    "apollo3_evb",
    "apollo3_evb_cygnus",
    "apollo3p_evb",
    "apollo3p_evb_cygnus",
    "apollo4l_evb",
    "apollo4l_blue_evb",
    "apollo4p_evb",
    "apollo4p_blue_kbr_evb",
    "apollo4p_blue_kxr_evb",
    "apollo5b_evb",
    "apollo510_evb",
    "apollo510b_evb",
    "apollo330mP_evb",
    "apollo510dL_evb",
)

# Load the packaged board descriptors. A malformed descriptor must NOT make
# this module (and therefore the whole package, including ``nsx doctor``)
# unimportable, so any load error is captured here and surfaced through
# :func:`validate_board_registry` instead of being raised at import time.
try:
    _DESCRIPTORS = load_board_descriptors()
    _DESCRIPTOR_LOAD_ERROR: str | None = None
except BoardDescriptorError as exc:  # pragma: no cover — exercised via doctor
    _DESCRIPTORS = {}
    _DESCRIPTOR_LOAD_ERROR = str(exc)


def validate_board_registry() -> list[str]:
    """Return board-registry problems, or an empty list if healthy.

    Centralizes the consistency checks that previously ran at import time
    and raised :class:`RuntimeError`. Callers such as ``nsx doctor`` invoke
    this and report problems gracefully instead of the whole package failing
    to import on a malformed or drifted descriptor set. The conditions are:

    * the packaged ``board.yaml`` descriptors loaded without error;
    * every name in ``_BOARD_ORDER`` ships a registered descriptor;
    * every registered descriptor is listed in ``_BOARD_ORDER``;
    * no two canonical board / SoC names collide under case-folding (see the
      case invariant documented above ``BOARDS``). This is the one place where
      the load-bearing case of identifiers like ``apollo330mP_evb`` /
      ``apollo330P`` cannot be normalized away: lowercasing is used both for
      input-boundary matching (``_BOARD_LOOKUP``) and as a downstream join key
      (the ``_board_lc`` CMake selector, ``nsx-board-…`` module names), so a
      casefold collision would silently dispatch to the wrong board.
    """

    problems: list[str] = []
    if _DESCRIPTOR_LOAD_ERROR is not None:
        problems.append(f"failed to load board descriptors: {_DESCRIPTOR_LOAD_ERROR}")
    missing = [b for b in _BOARD_ORDER if b not in _DESCRIPTORS]
    if missing:
        problems.append(
            f"_BOARD_ORDER references boards without a board.yaml descriptor: {missing}"
        )
    unordered = sorted(
        name
        for name, desc in _DESCRIPTORS.items()
        if desc.registered and name not in _BOARD_ORDER
    )
    if unordered:
        problems.append(
            f"registered board descriptors missing from _BOARD_ORDER: {unordered}"
        )
    problems.extend(_casefold_collisions("board", _BOARD_ORDER))
    problems.extend(
        _casefold_collisions(
            "SoC",
            dict.fromkeys(
                _DESCRIPTORS[b].soc for b in _BOARD_ORDER if b in _DESCRIPTORS
            ),
        )
    )
    return problems


def _casefold_collisions(kind: str, names: "Iterable[str]") -> list[str]:
    """Return a problem string per set of *names* that collapse under casefold.

    Canonical board / SoC identifiers carry load-bearing case (e.g.
    ``apollo330mP_evb``) yet are matched case-insensitively at input boundaries
    and lowercased to form downstream join keys. Two distinct names sharing a
    casefold therefore alias to a single lookup slot and silently dispatch to
    whichever one was inserted last. Folding to lowercase mirrors
    :data:`_BOARD_LOOKUP` / :data:`_SOC_LOOKUP` and the CMake ``_board_lc``
    selector.
    """

    buckets: dict[str, list[str]] = {}
    for name in names:
        buckets.setdefault(name.lower(), []).append(name)
    return [
        f"{kind} names collide under case-folding ({lowered!r}): {sorted(group)}"
        for lowered, group in buckets.items()
        if len(group) > 1
    ]


# Authoritative mapping from canonical board name to default SoC, derived from
# the board descriptors in the canonical order above. Built defensively (any
# board lacking a descriptor is skipped) so a drifted/broken registry is
# reported by :func:`validate_board_registry` rather than crashing import.
DEFAULT_SOC_FOR_BOARD = {
    b: _DESCRIPTORS[b].soc for b in _BOARD_ORDER if b in _DESCRIPTORS
}

# Canonical (case-correct) board identifiers.  Most are already lowercase, but
# ``apollo330mP_evb`` carries a load-bearing capital ``P`` (filesystem dir,
# CMake target name, package name in nsx-modules).  Inputs from the CLI / API
# / nsx.yml are normalized to these via :func:`normalize_board`.
#
# Case invariant (the contract behind every board/SoC string in NSX):
#   1. The canonical spelling here is the *single* internal form. The directory
#      under ``boards/`` (enforced by ``load_board_descriptors``) and the CMake
#      target alias use this exact case.
#   2. Case-insensitivity is confined to *input boundaries* — ``normalize_board``
#      / ``normalize_soc`` fold user input back to the canonical spelling before
#      it flows anywhere else, so internal code never needs case-insensitive
#      string-equality.
#   3. Lowercasing is *also* used as a downstream join key (``_BOARD_LOOKUP``,
#      the ``_board_lc`` CMake selector, ``nsx-board-…`` module names). For that
#      to be lossless the canonical names must be unique under case-folding —
#      ``validate_board_registry`` guards this so a future collision is reported
#      rather than silently dispatching to the wrong board.
BOARDS: tuple[str, ...] = tuple(DEFAULT_SOC_FOR_BOARD.keys())

# Canonical SoC identifiers (load-bearing case for ``apollo330P``).
SOCS: tuple[str, ...] = tuple(dict.fromkeys(DEFAULT_SOC_FOR_BOARD.values()))

# Lower-cased lookup tables for case-insensitive normalization at input
# boundaries.  Built once at import; never mutated.
_BOARD_LOOKUP: dict[str, str] = {b.lower(): b for b in BOARDS}
_SOC_LOOKUP: dict[str, str] = {s.lower(): s for s in SOCS}


def normalize_board(value: str | None) -> str | None:
    """Return the canonical spelling of *value* (case-insensitive match).

    Unknown boards are returned unchanged so the existing downstream
    error paths (e.g. SoC inference, board.cmake selection) can surface
    a domain-specific message.  Falsy inputs pass through unchanged.
    """

    if not value:
        return value
    return _BOARD_LOOKUP.get(value.lower(), value)


def normalize_soc(value: str | None) -> str | None:
    """Return the canonical spelling of *value* (case-insensitive match).

    Unknown SoCs are returned unchanged; see :func:`normalize_board`.
    """

    if not value:
        return value
    return _SOC_LOOKUP.get(value.lower(), value)


# ---------------------------------------------------------------------------
# Board → SDK provider mapping (single source of truth for R17)
# ---------------------------------------------------------------------------
#
# This dict is the authoritative mapping from canonical board name to the
# SDK provider name that supplies its low-level SDK payload. Today every
# registered board resolves to the single staged provider (``ambiqsuite``), but
# the descriptor field remains first-class Python metadata: the CLI / public
# API expose it, starter-profile derivation copies it through, and tests pin the
# current single-valued invariant explicitly.
#
# The CMake helper ``nsx_select_sdk_provider`` (in
# ``src/neuralspotx/cmake/nsx_sdk_providers.cmake``) now consumes the generated
# registered-board table ``nsx_board_table.cmake`` instead of mirroring this
# dict one-for-one, because the provider is currently single-valued on the CMake
# side. Drift between the Python board inventory and the committed CMake table
# is guarded by ``tests/test_board_table_drift.py``.

BOARD_SDK_PROVIDER: dict[str, str] = {
    b: _DESCRIPTORS[b].sdk_provider for b in _BOARD_ORDER if b in _DESCRIPTORS
}


class SDKProvider(str, enum.Enum):
    """Canonical SDK provider identifiers."""

    AMBIQSUITE = "ambiqsuite"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


SDK_PROVIDERS: frozenset[str] = frozenset(p.value for p in SDKProvider)


def board_sdk_provider(board: str | None) -> str | None:
    """Return the SDK provider name for *board*, or ``None`` if unknown.

    Accepts case-insensitive input via :func:`normalize_board`.
    """

    canonical = normalize_board(board)
    if not canonical:
        return None
    return BOARD_SDK_PROVIDER.get(canonical)


DEFAULT_TOOLCHAIN = "arm-none-eabi-gcc"

SUPPORTED_TOOLCHAINS = {
    "arm-none-eabi-gcc": "arm-none-eabi-gcc.cmake",
    "gcc": "arm-none-eabi-gcc.cmake",
    "armclang": "armclang.cmake",
    "atfe": "atfe.cmake",
}

# Toolchains that are functional but not yet fully validated for production use.
EXPERIMENTAL_TOOLCHAINS = {"atfe"}

# The project name used to identify modules that ship packaged with neuralspotx
# (boards, cmake helpers) vs external git-hosted modules.
PACKAGED_PROJECT_NAME = "neuralspotx"


# ---------------------------------------------------------------------------
# Toolchain enum
# ---------------------------------------------------------------------------


class Toolchain(str, enum.Enum):
    """Canonical toolchain identifiers.

    Mixed with ``str`` so existing code that compares ``toolchain == "gcc"``
    keeps working.  New code should prefer :meth:`Toolchain.parse` to
    accept user-supplied aliases (``gcc`` → ``arm-none-eabi-gcc``) and
    then use enum members for static checking.
    """

    GCC = "arm-none-eabi-gcc"
    ARMCLANG = "armclang"
    ATFE = "atfe"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value

    @classmethod
    def parse(cls, value: str) -> "Toolchain":
        """Resolve a CLI alias (``gcc``) or canonical name to a member.

        Raises ``ValueError`` for unknown values.
        """

        normalised = (value or "").strip().lower()
        if normalised in ("gcc", "arm-none-eabi-gcc"):
            return cls.GCC
        if normalised == "armclang":
            return cls.ARMCLANG
        if normalised == "atfe":
            return cls.ATFE
        raise ValueError(f"Unknown toolchain '{value}'. Allowed: {sorted(SUPPORTED_TOOLCHAINS)}")


# Public, hashable set of valid (canonical) toolchain identifiers.
TOOLCHAIN_VALUES: frozenset[str] = frozenset(t.value for t in Toolchain)
