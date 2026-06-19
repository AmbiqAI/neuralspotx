"""Shared NSX constants used by the CLI and library operations."""

from __future__ import annotations

import enum

from .board_descriptors import load_board_descriptors

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
)

_DESCRIPTORS = load_board_descriptors()

# Guard: every name in the canonical order must ship a registered descriptor,
# and every registered descriptor must be listed in the canonical order.
_missing_descriptor = [b for b in _BOARD_ORDER if b not in _DESCRIPTORS]
if _missing_descriptor:
    raise RuntimeError(
        f"_BOARD_ORDER references boards without a board.yaml descriptor: "
        f"{_missing_descriptor}"
    )
_unordered_registered = sorted(
    name
    for name, desc in _DESCRIPTORS.items()
    if desc.registered and name not in _BOARD_ORDER
)
if _unordered_registered:
    raise RuntimeError(
        f"registered board descriptors missing from _BOARD_ORDER: "
        f"{_unordered_registered}"
    )

# Authoritative mapping from canonical board name to default SoC, derived
# from the board descriptors in the canonical order above.
DEFAULT_SOC_FOR_BOARD = {b: _DESCRIPTORS[b].soc for b in _BOARD_ORDER}

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
# AmbiqSuite SDK provider name that supplies its low-level SDK payload. Its
# values are derived from the per-board ``board.yaml`` descriptors (the
# ``sdk_provider`` field), in the canonical board order.
#
# The CMake helper ``nsx_select_sdk_provider`` (in
# ``src/neuralspotx/cmake/nsx_sdk_providers.cmake``) consumes the
# generated CMake table ``nsx_board_table.cmake``, which is produced
# from this dict by ``scripts/gen_board_table.py``. Drift between the
# Python dict and the committed CMake table is guarded by
# ``tests/test_board_table_drift.py``.

BOARD_SDK_PROVIDER: dict[str, str] = {
    b: _DESCRIPTORS[b].sdk_provider for b in _BOARD_ORDER
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
