"""Shared NSX constants used by the CLI and library operations."""

from __future__ import annotations

DEFAULT_SOC_FOR_BOARD = {
    "apollo3_evb": "apollo3",
    "apollo3_evb_cygnus": "apollo3",
    "apollo3p_evb": "apollo3p",
    "apollo3p_evb_cygnus": "apollo3p",
    "apollo4l_evb": "apollo4l",
    "apollo4l_blue_evb": "apollo4l",
    "apollo4p_evb": "apollo4p",
    "apollo4p_blue_kbr_evb": "apollo4p",
    "apollo4p_blue_kxr_evb": "apollo4p",
    "apollo5b_evb": "apollo5b",
    "apollo510_evb": "apollo510",
    "apollo510b_evb": "apollo510b",
    "apollo330mP_evb": "apollo330P",
}

DEFAULT_TOOLCHAIN = "arm-none-eabi-gcc"
DEFAULT_REPO_NAME = "neuralspotx"

WEST_MANIFEST_TEMPLATE = """manifest:
  version: "0.13"

  projects:
    - name: "__NSX_REPO_NAME__"
      url: "__NSX_REPO_URL__"
      revision: "__NSX_REVISION__"
      path: "__NSX_REPO_NAME__"
__AMBIQ_PROJECT_BLOCK__  self:
    path: manifest
"""
