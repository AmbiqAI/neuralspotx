"""Shared NSX constants used by the CLI and library operations."""

from __future__ import annotations

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
}

DEFAULT_TOOLCHAIN = "arm-none-eabi-gcc"

SUPPORTED_TOOLCHAINS = {
    "arm-none-eabi-gcc": "arm-none-eabi-gcc.cmake",
    "gcc": "arm-none-eabi-gcc.cmake",
    "armclang": "armclang.cmake",
}

# The project name used to identify modules that ship packaged with neuralspotx
# (boards, cmake helpers) vs external git-hosted modules.
PACKAGED_PROJECT_NAME = "neuralspotx"
