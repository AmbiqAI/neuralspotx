"""Phase 4: derived starter profiles from soc_family baselines.

The packaged ``registry.lock.yaml`` no longer enumerates a full module
list per board (nor the unused ``compat_matrix``). Instead it declares
per-family baselines plus a per-board channel, and
``metadata._derive_starter_profiles`` expands them. These tests lock that
expansion and the tolerant validation behaviour.
"""

from __future__ import annotations

from importlib import resources

import pytest

from neuralspotx.metadata import _derive_starter_profiles, load_registry_lock


def _packaged_registry() -> dict:
    res = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(res) as path:
        return load_registry_lock(path)


def test_packaged_lock_has_no_compat_matrix_or_literal_profiles() -> None:
    res = resources.files("neuralspotx.data").joinpath("registry.lock.yaml")
    with resources.as_file(res) as path:
        text = path.read_text(encoding="utf-8")
    assert "compat_matrix" not in text
    # Profiles are derived, not enumerated.
    assert "_minimal" not in text
    assert "soc_families:" in text
    assert "board_profiles:" in text


def test_derived_profiles_cover_all_board_profiles() -> None:
    reg = _packaged_registry()
    profiles = reg["starter_profiles"]
    assert len(profiles) == len(reg["board_profiles"])
    for board in reg["board_profiles"]:
        assert f"{board}_minimal" in profiles


def test_derived_profile_module_layout() -> None:
    reg = _packaged_registry()
    prof = reg["starter_profiles"]["apollo510_evb_minimal"]
    family = reg["soc_families"]["r5"]
    core = family.get("core_modules", reg["profile_defaults"]["core_modules"])
    assert prof["board"] == "apollo510_evb"
    assert prof["soc"] == "apollo510"
    assert prof["channel"] == "stable"
    assert prof["modules"] == [
        *family["modules"],
        "nsx-board-apollo510-evb",
        *core,
    ]
    # R5 is sourced from the consolidated nsx-ambiq-sdk monorepo: the
    # project override pins the monorepo and every module the monorepo
    # vendors gets a module override pointing back at it.
    assert prof["project_overrides"] == {"nsx-ambiq-sdk": {"revision": "main"}}
    assert set(prof["module_overrides"]) == set(family["sdk_modules"])
    assert prof["module_overrides"]["nsx-ambiqsuite-r5"] == {
        "project": "nsx-ambiq-sdk",
        "revision": "main",
        "metadata": "modules/nsx-ambiqsuite-r5/nsx-module.yaml",
    }
    # A shared-name module (also vendored by the monorepo) resolves to the
    # tier-correct monorepo source rather than its standalone repo.
    assert prof["module_overrides"]["nsx-soc-hal"]["project"] == "nsx-ambiq-sdk"
    assert "nsx-pmu-armv8m" not in prof["module_overrides"]
    assert "nsx-cmsis-core" in prof["modules"]
    assert "nsx-pmu-armv8m" in prof["modules"]


def test_non_r5_profiles_do_not_gain_armv8m_pmu() -> None:
    reg = _packaged_registry()
    prof = reg["starter_profiles"]["apollo4p_evb_minimal"]
    assert "nsx-cmsis-core" in prof["modules"]
    assert "nsx-pmu-armv8m" not in prof["modules"]


def test_channel_defaulting_and_override() -> None:
    reg = _packaged_registry()
    # board_profiles entry with no channel inherits profile_defaults.channel.
    assert reg["starter_profiles"]["apollo3_evb_minimal"]["channel"] == "stable"
    # explicit channel override wins.
    assert reg["starter_profiles"]["apollo5b_evb_minimal"]["channel"] == "preview"


def test_board_module_name_lowercased() -> None:
    reg = _packaged_registry()
    prof = reg["starter_profiles"]["apollo510dL_evb_minimal"]
    assert "nsx-board-apollo510dl-evb" in prof["modules"]


def test_unknown_family_raises() -> None:
    data = {
        "profile_defaults": {"toolchain": "arm-none-eabi-gcc", "channel": "stable", "core_modules": []},
        "soc_families": {"r5": {"provider": "p", "revision": "v", "modules": []}},
        "board_profiles": {"apollo3_evb": {}},  # apollo3_evb is an r3 board
    }
    with pytest.raises(ValueError, match="unknown soc family"):
        _derive_starter_profiles(data)


def test_unknown_board_descriptor_raises() -> None:
    data = {
        "profile_defaults": {"channel": "stable", "core_modules": []},
        "soc_families": {"r5": {"provider": "p", "revision": "v", "modules": []}},
        "board_profiles": {"not_a_board": {}},
    }
    with pytest.raises(ValueError, match="no board descriptor"):
        _derive_starter_profiles(data)


def test_literal_starter_profiles_still_accepted() -> None:
    """A minimal registry without family sections keeps literal profiles."""

    import tempfile
    from pathlib import Path

    text = (
        "schema_version: 1\n"
        "channels: {}\n"
        "projects: {}\n"
        "modules: {}\n"
        "starter_profiles: {}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "registry.lock.yaml"
        path.write_text(text, encoding="utf-8")
        reg = load_registry_lock(path)
    assert reg["starter_profiles"] == {}
