"""Shared NSX constants used by the CLI and library operations."""

from __future__ import annotations

import enum

DEFAULT_SOC_FOR_BOARD = {
    "apollo3_evb": "apollo3",
    "apollo3_evb_cygnus": "apollo3",
    "apollo3p_evb": "apollo3p",
    "apollo3p_evb_cygnus": "apollo3p",
    "apollo4l_evb": "apollo4l",
    "apollo4l_blue_evb": "apollo4l",
    "apollo4b_blue_evb": "apollo4p",
    "apollo4p_evb": "apollo4p",
    "apollo4p_blue_kbr_evb": "apollo4p",
    "apollo4p_blue_kxr_evb": "apollo4p",
    "apollo5b_evb": "apollo5b",
    "apollo510_evb": "apollo510",
    "apollo510b_evb": "apollo510b",
    "apollo330mP_evb": "apollo330P",
    "atomiq110_fpga_turbo": "atomiq110",
}

# Canonical (case-correct) board identifiers.  Most are already lowercase, but
# ``apollo330mP_evb`` carries a load-bearing capital ``P`` (filesystem dir,
# CMake target name, package name in nsx-modules).  Inputs from the CLI / API
# / nsx.yml are normalized to these via :func:`normalize_board`.
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
# AmbiqSuite SDK provider module that supplies its low-level SDK payload.
#
# The CMake helper ``nsx_select_sdk_provider`` (in
# ``src/neuralspotx/cmake/nsx_sdk_providers.cmake``) consumes the
# generated CMake table ``nsx_board_table.cmake``, which is produced
# from this dict by ``scripts/gen_board_table.py``. Drift between the
# Python dict and the committed CMake table is guarded by
# ``tests/test_board_table_drift.py``.

BOARD_SDK_PROVIDER: dict[str, str] = {
    "apollo3_evb": "ambiqsuite-r3",
    "apollo3_evb_cygnus": "ambiqsuite-r3",
    "apollo3p_evb": "ambiqsuite-r3",
    "apollo3p_evb_cygnus": "ambiqsuite-r3",
    "apollo4l_evb": "ambiqsuite-r4",
    "apollo4l_blue_evb": "ambiqsuite-r4",
    "apollo4b_blue_evb": "ambiqsuite-r4",
    "apollo4p_evb": "ambiqsuite-r4",
    "apollo4p_blue_kbr_evb": "ambiqsuite-r4",
    "apollo4p_blue_kxr_evb": "ambiqsuite-r4",
    "apollo5b_evb": "ambiqsuite-r5",
    "apollo510_evb": "ambiqsuite-r5",
    "apollo510b_evb": "ambiqsuite-r5",
    "apollo330mP_evb": "ambiqsuite-r5",
    "atomiq110_fpga_turbo": "ambiqsuite-r6",
}


class SDKProvider(str, enum.Enum):
    """Canonical SDK provider identifiers."""

    R3 = "ambiqsuite-r3"
    R4 = "ambiqsuite-r4"
    R5 = "ambiqsuite-r5"
    R6 = "ambiqsuite-r6"

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
