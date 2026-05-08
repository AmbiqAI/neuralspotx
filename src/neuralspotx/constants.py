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
    "apollo330mp_evb": "apollo330P",  # lowercase alias for convenience
}

DEFAULT_TOOLCHAIN = "arm-none-eabi-gcc"

SUPPORTED_TOOLCHAINS = {
    "arm-none-eabi-gcc": "arm-none-eabi-gcc.cmake",
    "gcc": "arm-none-eabi-gcc.cmake",
    "armclang": "armclang.cmake",
    "atfe": "atfe.cmake",
}

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
