"""Per-target compatibility enforcement + bypass (#135 step 4).

Per-target compatibility is enforced in the dependency-closure resolver:
each resolved module's ``compatibility`` block (``boards`` / ``socs`` /
``toolchains``, ``"*"`` = any) is intersected against the active target, and
an incompatible module raises ``NSXModuleError``. ``NSX_SKIP_COMPAT_CHECK=1``
is the documented emergency bypass and must be honored at this single
enforcement site.
"""

from __future__ import annotations

import pytest

from neuralspotx._errors import NSXModuleError
from neuralspotx.models import ModuleMetadata
from neuralspotx.module_registry import _closure


def _meta(boards: list[str], socs: list[str], toolchains: list[str]) -> dict:
    return {
        "module": {"name": "m", "type": "library", "version": "0.0.0"},
        "support": {"ambiqsuite": True, "zephyr": False},
        "depends": {"required": [], "optional": []},
        "compatibility": {"boards": boards, "socs": socs, "toolchains": toolchains},
    }


def _resolve(
    meta: dict,
    monkeypatch,
    *,
    board: str = "apollo510_evb",
    soc: str = "apollo510",
    tc: str = "arm-none-eabi-gcc",
) -> list[str]:
    monkeypatch.setattr(
        _closure, "_load_module_metadata",
        lambda name, registry, app_dir=None: ModuleMetadata.from_raw(meta),
    )
    return _closure._resolve_module_closure(
        ["m"],
        app_dir=None,
        nsx_cfg={
            "target": {"board": board, "soc": soc},
            "toolchain": tc,
            "modules": [{"name": "m"}],
        },
        registry={},
        default_toolchain=tc,
    )


# --- env-flag parsing -----------------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_skip_flag_truthy_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("NSX_SKIP_COMPAT_CHECK", value)
    assert _closure._compat_check_skipped() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "nope"])
def test_skip_flag_falsy_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv("NSX_SKIP_COMPAT_CHECK", value)
    assert _closure._compat_check_skipped() is False


# --- enforcement in the resolver ------------------------------------------


def test_compatible_target_resolves(monkeypatch) -> None:
    monkeypatch.delenv("NSX_SKIP_COMPAT_CHECK", raising=False)
    assert _resolve(
        _meta(["apollo510_evb"], ["apollo510"], ["arm-none-eabi-gcc"]), monkeypatch
    ) == ["m"]


def test_wildcard_resolves(monkeypatch) -> None:
    monkeypatch.delenv("NSX_SKIP_COMPAT_CHECK", raising=False)
    assert _resolve(_meta(["*"], ["*"], ["*"]), monkeypatch) == ["m"]


def test_incompatible_soc_raises(monkeypatch) -> None:
    monkeypatch.delenv("NSX_SKIP_COMPAT_CHECK", raising=False)
    with pytest.raises(NSXModuleError) as exc:
        _resolve(_meta(["*"], ["apollo4p"], ["*"]), monkeypatch, soc="apollo510")
    assert "incompatible" in str(exc.value)
    assert "NSX_SKIP_COMPAT_CHECK" in str(exc.value)


def test_incompatible_board_raises(monkeypatch) -> None:
    monkeypatch.delenv("NSX_SKIP_COMPAT_CHECK", raising=False)
    with pytest.raises(NSXModuleError):
        _resolve(
            _meta(["apollo4p_blue_kxr_evb"], ["*"], ["*"]), monkeypatch, board="apollo510_evb"
        )


def test_skip_env_bypasses_incompatible_module(monkeypatch) -> None:
    # The emergency bypass must be honored at the resolver, the single
    # enforcement site, so an otherwise-incompatible module resolves.
    monkeypatch.setenv("NSX_SKIP_COMPAT_CHECK", "1")
    assert _resolve(_meta(["nope"], ["nope"], ["nope"]), monkeypatch) == ["m"]
