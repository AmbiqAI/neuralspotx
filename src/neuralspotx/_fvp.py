"""Arm FVP profiles used by the runner and generated applications."""

from dataclasses import dataclass


@dataclass(frozen=True)
class _Fvp:
    executable: str
    board_component: str
    settings: tuple[str, ...]


FVP_MODELS = {
    "corstone300_fvp_u55": _Fvp(
        "FVP_Corstone_SSE-300_Ethos-U55",
        "mps3_board",
        (
            "cpu0.CFGDTCMSZ=12",
            "cpu0.CFGITCMSZ=12",
            "ethosu.num_macs=32",
        ),
    ),
    "corstone310_fvp_u55": _Fvp("FVP_Corstone_SSE-310", "mps3_board", ("ethosu.num_macs=32",)),
    "corstone320_fvp_u85": _Fvp(
        "FVP_Corstone_SSE-320",
        "mps4_board",
        (
            "vis_hdlcd.disable_visualisation=1",
            "mps4_board.subsystem.ethosu.num_macs=256",
        ),
    ),
}
