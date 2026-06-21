"""Per-target compatibility validation at lock time (#135 step 4).

When a board is locked, every resolved module's ``compatibility`` block
(``boards`` / ``socs`` / ``toolchains``, ``"*"`` = any) is intersected
against that target. A board listed in ``targets.supported`` that a required
module does not actually support fails ``nsx lock`` fast, instead of becoming
a cryptic downstream build error.
"""

from __future__ import annotations

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.operations import _lock


def _meta(boards: list[str], socs: list[str], toolchains: list[str]) -> dict:
    return {
        "module": {"name": "m", "type": "library", "version": "0.0.0"},
        "compatibility": {"boards": boards, "socs": socs, "toolchains": toolchains},
    }


def _patch_metadata(monkeypatch, table: dict[str, dict]) -> None:
    def fake_load(name, registry, app_dir=None):
        if name not in table:
            raise KeyError(name)
        return table[name]

    monkeypatch.setattr(_lock, "_load_module_metadata", fake_load)


def _validate(table, monkeypatch, *, board="apollo510_evb", soc="apollo510", tc="arm-none-eabi-gcc"):
    _patch_metadata(monkeypatch, table)
    _lock._validate_target_compatibility(
        list(table),
        {},
        board=board,
        soc=soc,
        toolchain=tc,
        app_dir=None,  # type: ignore[arg-type]
    )


def test_compatible_target_passes(monkeypatch) -> None:
    table = {"m": _meta(["apollo510_evb"], ["apollo510"], ["arm-none-eabi-gcc"])}
    _validate(table, monkeypatch)  # no raise


def test_wildcard_board_passes(monkeypatch) -> None:
    table = {"m": _meta(["*"], ["apollo510"], ["arm-none-eabi-gcc"])}
    _validate(table, monkeypatch)  # no raise


def test_incompatible_soc_raises(monkeypatch) -> None:
    table = {"m": _meta(["*"], ["apollo4p"], ["arm-none-eabi-gcc"])}
    with pytest.raises(NSXConfigError) as exc:
        _validate(table, monkeypatch, soc="apollo510")
    msg = str(exc.value)
    assert "m" in msg
    assert "soc=" in msg


def test_incompatible_board_raises(monkeypatch) -> None:
    table = {"m": _meta(["apollo4p_blue_kxr_evb"], ["*"], ["*"])}
    with pytest.raises(NSXConfigError) as exc:
        _validate(table, monkeypatch, board="apollo510_evb")
    assert "board=" in str(exc.value)


def test_incompatible_lists_every_offending_module(monkeypatch) -> None:
    table = {
        "ok": _meta(["*"], ["*"], ["*"]),
        "bad1": _meta(["*"], ["apollo4p"], ["*"]),
        "bad2": _meta(["apollo330mP_evb"], ["*"], ["*"]),
    }
    with pytest.raises(NSXConfigError) as exc:
        _validate(table, monkeypatch)
    msg = str(exc.value)
    assert "bad1" in msg and "bad2" in msg
    assert "ok" not in msg.split("incompatible")[-1]


def test_env_bypass_skips_check(monkeypatch) -> None:
    monkeypatch.setenv("NSX_SKIP_COMPAT_CHECK", "1")
    table = {"m": _meta(["nope"], ["nope"], ["nope"])}
    _validate(table, monkeypatch)  # no raise despite mismatch


def test_missing_metadata_is_skipped(monkeypatch) -> None:
    # Loader raises (e.g. clean-checkout --check): module is skipped, not failed.
    def raising_load(name, registry, app_dir=None):
        raise KeyError(name)

    monkeypatch.setattr(_lock, "_load_module_metadata", raising_load)
    _lock._validate_target_compatibility(
        ["m"],
        {},
        board="apollo510_evb",
        soc="apollo510",
        toolchain="arm-none-eabi-gcc",
        app_dir=None,  # type: ignore[arg-type]
    )  # no raise


def test_unknown_soc_without_board_target_is_noop(monkeypatch) -> None:
    # No soc resolved -> cannot assess; do not raise.
    table = {"m": _meta(["nope"], ["nope"], ["nope"])}
    _patch_metadata(monkeypatch, table)
    _lock._validate_target_compatibility(
        ["m"], {}, board="apollo510_evb", soc=None, toolchain="x", app_dir=None  # type: ignore[arg-type]
    )  # no raise
