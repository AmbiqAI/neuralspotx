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
        "schema_version": 2,
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
        "schema_version": 2,
        "project": {"name": "demo"},
        "target": {"board": "apollo510_evb"},
        "profile": "apollo510_evb_custom",
    })
    assert cfg.resolve_target().profile == "apollo510_evb_custom"


def test_no_target_resolves_empty() -> None:
    cfg = _cfg({"schema_version": 2, "project": {"name": "demo"}})
    assert cfg.targets() == {}
    assert cfg.default_board() is None
    with pytest.raises(NSXConfigError):
        cfg.resolve_target()


# --- explicit targets: block ---------------------------------------------


def test_targets_supported_as_list_defaults_profiles() -> None:
    cfg = _cfg({
        "schema_version": 2,
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
        "schema_version": 2,
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
        "schema_version": 2,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb", "apollo510b_evb"]},
    })
    assert cfg.default_board() == "apollo510_evb"


def test_resolve_unsupported_board_raises() -> None:
    cfg = _cfg({
        "schema_version": 2,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb"]},
    })
    with pytest.raises(NSXConfigError):
        cfg.resolve_target("apollo4p_evb")


def test_block_inherits_singular_soc_for_default_board() -> None:
    cfg = _cfg({
        "schema_version": 2,
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
        "schema_version": 2,
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
            "schema_version": 2,
            "project": {"name": "demo"},
            "targets": targets,
        })


def test_loader_rejects_top_level_requires() -> None:
    # The additive ``requires:`` field was removed in schema v2; dependencies
    # live under a single ``modules:`` list. The loader rejects it outright.
    with pytest.raises(NSXConfigError, match="no longer supported") as exc_info:
        NsxProject.from_mapping({
            "schema_version": 2,
            "project": {"name": "demo"},
            "target": {"board": "apollo510_evb"},
            "requires": ["nsx-usb"],
        })
    assert exc_info.value.field == "requires"


def test_loader_rejects_per_target_requires() -> None:
    # A per-target ``requires:`` is equally rejected; per-board scoping is now
    # expressed with a ``boards:`` filter on a ``modules:`` entry.
    with pytest.raises(NSXConfigError, match="no longer supported") as exc_info:
        NsxProject.from_mapping({
            "schema_version": 2,
            "project": {"name": "demo"},
            "targets": {
                "default": "apollo510_evb",
                "supported": {
                    "apollo510_evb": {"requires": ["nsx-ambiq-usb"]},
                    "apollo510b_evb": {},
                },
            },
        })
    assert exc_info.value.field == "targets.supported.apollo510_evb.requires"


def test_resolve_target_tolerates_noncanonical_board_spelling() -> None:
    # The build path resolves with a normalize_board-d name; resolution must
    # still match a target keyed by the raw (here differently-cased) spelling.
    cfg = _cfg({
        "schema_version": 2,
        "project": {"name": "demo"},
        "targets": {"supported": ["apollo510_evb"]},
    })
    assert cfg.resolve_target("APOLLO510_EVB").board == "apollo510_evb"


def test_configure_uses_per_board_target_toolchain(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A per-board ``targets.supported.<board>.toolchain`` must drive the
    # CMake toolchain file at configure time, not just the top-level default.
    from neuralspotx import project_config
    from neuralspotx.constants import SUPPORTED_TOOLCHAINS

    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\n"
        "project:\n  name: demo\n"
        "toolchain: arm-none-eabi-gcc\n"
        "targets:\n"
        "  default: apollo510_evb\n"
        "  supported:\n"
        "    apollo510_evb: {}\n"
        "    apollo510b_evb: { toolchain: armclang }\n",
        encoding="utf-8",
    )

    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(project_config, "run", lambda cmd: captured.setdefault("cmd", cmd))

    project_config._run_cmake_configure(tmp_path, tmp_path / "build", "apollo510b_evb")
    cmd = captured["cmd"]
    tc_arg = next(a for a in cmd if a.startswith("-DCMAKE_TOOLCHAIN_FILE="))
    assert SUPPORTED_TOOLCHAINS["armclang"] in tc_arg

    captured.clear()
    project_config._run_cmake_configure(tmp_path, tmp_path / "build", "apollo510_evb")
    tc_arg = next(a for a in captured["cmd"] if a.startswith("-DCMAKE_TOOLCHAIN_FILE="))
    assert SUPPORTED_TOOLCHAINS["arm-none-eabi-gcc"] in tc_arg


def test_configure_falls_back_to_top_level_toolchain_for_unknown_board(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A board outside the declared targets falls back to the top-level
    # toolchain rather than raising.
    from neuralspotx import project_config
    from neuralspotx.constants import SUPPORTED_TOOLCHAINS

    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\n"
        "project:\n  name: demo\n"
        "toolchain: armclang\n"
        "targets:\n"
        "  default: apollo510_evb\n"
        "  supported:\n    apollo510_evb: {}\n",
        encoding="utf-8",
    )

    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(project_config, "run", lambda cmd: captured.setdefault("cmd", cmd))

    project_config._run_cmake_configure(tmp_path, tmp_path / "build", "apollo330mP_evb")
    tc_arg = next(a for a in captured["cmd"] if a.startswith("-DCMAKE_TOOLCHAIN_FILE="))
    assert SUPPORTED_TOOLCHAINS["armclang"] in tc_arg


def test_cmake_configure_propagates_jlink_path_override(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neuralspotx import project_config

    commander = tmp_path / "SEGGER tools" / "JLink.exe"
    commander.parent.mkdir()
    commander.write_bytes(b"")
    monkeypatch.setenv("JLINK_PATH", str(commander))
    captured: dict[str, list[str]] = {}
    monkeypatch.setattr(project_config, "run", lambda cmd: captured.setdefault("cmd", cmd))

    project_config._run_cmake_configure(tmp_path, tmp_path / "build", "apollo510_evb")

    assert f"-DNSX_JLINK_EXE:FILEPATH={commander}" in captured["cmd"]


def test_cmake_configure_clears_probe_and_missing_jlink_cache(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neuralspotx import project_config

    captured: dict[str, list[str]] = {}
    monkeypatch.delenv("JLINK_PATH", raising=False)
    monkeypatch.setattr(project_config, "find_segger_tool", lambda _names: None)
    monkeypatch.setattr(project_config, "run", lambda cmd: captured.setdefault("cmd", cmd))

    project_config._run_cmake_configure(tmp_path, tmp_path / "build", "apollo510_evb")

    assert "-DNSX_JLINK_SERIAL=" in captured["cmd"]
    assert "-DNSX_JLINK_EXE:FILEPATH=NSX_JLINK_EXE-NOTFOUND" in captured["cmd"]
