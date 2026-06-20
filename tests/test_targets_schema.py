"""Multi-target schema: ``targets:`` block + single-target back-compat.

An app manifest may declare several build targets under a ``targets:``
block, or keep the legacy singular ``target:`` / ``profile:`` keys.
``AppConfig.targets()`` resolves both shapes to a uniform mapping of
board name -> :class:`ResolvedTarget`, with ``profile`` defaulting to the
board's derived starter profile (``<board>_minimal``).
"""

from __future__ import annotations

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.models import AppConfig, ResolvedTarget
from neuralspotx.models._loader import NsxProject


def _cfg(raw: dict) -> AppConfig:
    return AppConfig.from_mapping(raw)


# --- single-target back-compat -------------------------------------------


def test_singular_target_derives_one_resolved_target() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
    })
    targets = cfg.targets()
    assert targets == {
        "apollo510_evb": ResolvedTarget(
            board="apollo510_evb",
            soc="apollo510",
            profile="apollo510_evb_minimal",
            toolchain="arm-none-eabi-gcc",
        )
    }
    assert cfg.default_board() == "apollo510_evb"


def test_singular_target_honours_explicit_profile() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": "apollo510_evb"},
        "profile": "apollo510_evb_custom",
    })
    assert cfg.resolve_target().profile == "apollo510_evb_custom"


def test_no_target_resolves_empty() -> None:
    cfg = _cfg({"schema_version": 1, "project": {"name": "demo"}})
    assert cfg.targets() == {}
    assert cfg.default_board() is None
    with pytest.raises(NSXConfigError):
        cfg.resolve_target()


# --- explicit targets: block ---------------------------------------------


def test_targets_supported_as_list_defaults_profiles() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "toolchain": "arm-none-eabi-gcc",
        "targets": {
            "default": "apollo510_evb",
            "supported": ["apollo510_evb", "apollo510b_evb"],
        },
    })
    targets = cfg.targets()
    assert set(targets) == {"apollo510_evb", "apollo510b_evb"}
    assert targets["apollo510b_evb"] == ResolvedTarget(
        board="apollo510b_evb",
        soc=None,
        profile="apollo510b_evb_minimal",
        toolchain="arm-none-eabi-gcc",
    )
    assert cfg.default_board() == "apollo510_evb"


def test_targets_supported_as_mapping_with_overrides() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "toolchain": "arm-none-eabi-gcc",
        "targets": {
            "default": "apollo510_evb",
            "supported": {
                "apollo510_evb": {"soc": "apollo510"},
                "apollo510b_evb": {
                    "profile": "apollo510b_evb_full",
                    "toolchain": "armclang",
                },
            },
        },
    })
    targets = cfg.targets()
    assert targets["apollo510_evb"].soc == "apollo510"
    assert targets["apollo510_evb"].profile == "apollo510_evb_minimal"
    assert targets["apollo510_evb"].toolchain == "arm-none-eabi-gcc"
    assert targets["apollo510b_evb"].profile == "apollo510b_evb_full"
    assert targets["apollo510b_evb"].toolchain == "armclang"


def test_default_board_falls_back_to_first_supported() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb", "apollo510b_evb"]},
    })
    assert cfg.default_board() == "apollo510_evb"


def test_resolve_unsupported_board_raises() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb"]},
    })
    with pytest.raises(NSXConfigError):
        cfg.resolve_target("apollo4p_evb")


def test_block_inherits_singular_soc_for_default_board() -> None:
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "targets": {"supported": ["apollo510_evb", "apollo510b_evb"]},
    })
    targets = cfg.targets()
    assert targets["apollo510_evb"].soc == "apollo510"
    assert targets["apollo510b_evb"].soc is None


# --- loader validation ----------------------------------------------------


def test_loader_accepts_targets_block() -> None:
    proj = NsxProject.from_mapping({
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {
            "default": "apollo510_evb",
            "supported": ["apollo510_evb", "apollo510b_evb"],
        },
    })
    assert proj.supported_boards == ["apollo510_evb", "apollo510b_evb"]
    assert proj.default_board == "apollo510_evb"


@pytest.mark.parametrize(
    "targets",
    [
        {"supported": "apollo510_evb"},  # not a list/mapping
        {"supported": [123]},  # non-string list entry
        {"default": 5},  # non-string default
        {"supported": {"apollo510_evb": {"soc": 7}}},  # non-string override
        {"default": "apollo4p_evb", "supported": ["apollo510_evb"]},  # default not supported
    ],
)
def test_loader_rejects_malformed_targets(targets: dict) -> None:
    with pytest.raises(NSXConfigError):
        NsxProject.from_mapping({
            "schema_version": 1,
            "project": {"name": "demo"},
            "targets": targets,
        })


def test_loader_accepts_requires() -> None:
    proj = NsxProject.from_mapping({
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {
            "default": "apollo510_evb",
            "supported": {
                "apollo510_evb": {"requires": ["nsx-ambiq-usb"]},
                "apollo510b_evb": {},
            },
        },
        "requires": ["nsx-usb", {"name": "nsx-timer", "project": "p", "revision": "r"}],
    })
    assert proj.default_board == "apollo510_evb"


@pytest.mark.parametrize(
    "raw",
    [
        {"requires": "nsx-usb"},  # not a list
        {"requires": [123]},  # non-string entry
        {"requires": [{"project": "p"}]},  # mapping missing name
        {"requires": [{"name": "nsx-usb", "project": 5}]},  # non-string project
    ],
)
def test_loader_rejects_malformed_requires(raw: dict) -> None:
    with pytest.raises(NSXConfigError):
        NsxProject.from_mapping({
            "schema_version": 1,
            "project": {"name": "demo"},
            "targets": {"supported": ["apollo510_evb"]},
            **raw,
        })


def test_loader_rejects_modules_and_requires_together() -> None:
    with pytest.raises(NSXConfigError, match="mutually exclusive"):
        NsxProject.from_mapping({
            "schema_version": 1,
            "project": {"name": "demo"},
            "target": {"board": "apollo510_evb"},
            "modules": [{"name": "nsx-core"}],
            "requires": ["nsx-usb"],
        })


def test_resolve_target_tolerates_noncanonical_board_spelling() -> None:
    # The build path resolves with a normalize_board-d name; resolution must
    # still match a target keyed by the raw (here differently-cased) spelling.
    cfg = _cfg({
        "schema_version": 1,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb"]},
    })
    assert cfg.resolve_target("APOLLO510_EVB").board == "apollo510_evb"
