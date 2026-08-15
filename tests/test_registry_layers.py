"""Tests for layered registry resolution (``registry.layers`` in nsx.yml)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.project_config import (
    _effective_registry,
    validate_app_module_alignment,
)


def _base_registry() -> dict:
    return {
        "projects": {"nsx-core": {"name": "nsx-core", "revision": "v1"}},
        "modules": {"nsx-core": {"project": "nsx-core", "revision": "v1"}},
    }


def test_no_registry_block_is_identity_plus_legacy_override() -> None:
    """Apps without a ``registry:`` block behave exactly as before."""

    base = _base_registry()
    nsx_cfg: dict = {}
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "v1"


def test_legacy_module_registry_still_applies() -> None:
    base = _base_registry()
    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-core": {"revision": "override"}},
        }
    }
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "override"


def test_packaged_layer_is_noop() -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": ["packaged"]}}
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "v1"


def test_inline_layer_overrides_base() -> None:
    base = _base_registry()
    nsx_cfg = {
        "registry": {
            "layers": [
                "packaged",
                {"inline": {"projects": {"nsx-core": {"revision": "from-inline"}}}},
            ]
        }
    }
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "from-inline"


def test_layers_apply_in_order_last_wins() -> None:
    base = _base_registry()
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-core": {"revision": "first"}}}},
                {"inline": {"projects": {"nsx-core": {"revision": "second"}}}},
            ]
        }
    }
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "second"


def test_legacy_block_wins_over_layers() -> None:
    """The top-level ``module_registry`` keeps its historical precedence."""

    base = _base_registry()
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-core": {"revision": "layer"}}}},
            ]
        },
        "module_registry": {"projects": {"nsx-core": {"revision": "legacy"}}},
    }
    out = _effective_registry(base, nsx_cfg)
    assert out["projects"]["nsx-core"]["revision"] == "legacy"


def test_layers_win_over_synthetic_profile_defaults() -> None:
    base = _base_registry()
    nsx_cfg = {
        "_profile_registry": {
            "projects": {"nsx-core": {"revision": "profile"}},
        },
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-core": {"revision": "layer"}}}},
            ]
        },
    }

    out = _effective_registry(base, nsx_cfg)

    assert out["projects"]["nsx-core"]["revision"] == "layer"


def test_workspace_layer_reads_overlay_file(tmp_path: Path) -> None:
    overlay = tmp_path / "nsx-registry.yaml"
    overlay.write_text(
        textwrap.dedent(
            """
            schema_version: 1
            projects:
              nsx-core:
                local_path: ../../shared/nsx-core
            modules:
              nsx-extra:
                project: nsx-extra
                revision: v9
            """
        ),
        encoding="utf-8",
    )
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": [{"workspace": "nsx-registry.yaml"}]}}
    out = _effective_registry(base, nsx_cfg, app_dir=tmp_path)
    assert out["projects"]["nsx-core"]["local_path"] == str(
        (tmp_path / "../../shared/nsx-core").resolve()
    )
    assert out["modules"]["nsx-extra"]["revision"] == "v9"


def test_workspace_layer_missing_file_raises(tmp_path: Path) -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": [{"workspace": "does-not-exist.yaml"}]}}
    with pytest.raises(NSXConfigError) as exc:
        _effective_registry(base, nsx_cfg, app_dir=tmp_path)
    assert exc.value.field == "registry.layers"


def test_layers_must_be_a_list() -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": {"inline": {}}}}
    with pytest.raises(NSXConfigError):
        _effective_registry(base, nsx_cfg)


def test_unknown_layer_kind_raises() -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": [{"bogus": {}}]}}
    with pytest.raises(NSXConfigError):
        _effective_registry(base, nsx_cfg)


def test_unknown_string_layer_raises() -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": ["frobnicate"]}}
    with pytest.raises(NSXConfigError):
        _effective_registry(base, nsx_cfg)


def test_multi_key_layer_mapping_raises() -> None:
    base = _base_registry()
    nsx_cfg = {"registry": {"layers": [{"inline": {}, "workspace": "x"}]}}
    with pytest.raises(NSXConfigError):
        _effective_registry(base, nsx_cfg)


# --- app project pins vs packaged module revisions (issue #218) ------------


_PIN = "c219a2bc98c62f96819fae20ab6c8911fcea3e25"


def _sensors_base_registry() -> dict:
    """Packaged-shaped base: project and module both at the packaged default."""

    return {
        "projects": {
            "nsx-sensors": {
                "name": "nsx-sensors",
                "url": "https://github.com/AmbiqAI/nsx-sensors.git",
                "revision": "v0.1.0",
                "path": "modules/nsx-sensors",
            },
            "other-proj": {"name": "other-proj", "revision": "v3.0.0"},
        },
        "modules": {
            "nsx-sensors": {
                "project": "nsx-sensors",
                "revision": "v0.1.0",
                "metadata": "modules/nsx-sensors/nsx-module.yaml",
            },
            "other-mod": {
                "project": "other-proj",
                "revision": "v3.0.0",
                "metadata": "modules/other-mod/nsx-module.yaml",
            },
        },
    }


def test_app_project_pin_beats_packaged_module_revision() -> None:
    """An app-local project pin wins over the packaged module-level default.

    Reproduces AmbiqAI/neuralspotx#218: the manifest pinned the project at a
    commit while the packaged registry's module entry still said ``v0.1.0``,
    and the module-level entry from the *lower-precedence* source silently
    won.
    """

    from neuralspotx.metadata import registry_entry_for_module

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["projects"]["nsx-sensors"]["revision"] == _PIN
    assert out["modules"]["nsx-sensors"]["revision"] == _PIN
    # Bind the assertion to the exact accessor the lock/acquire paths use.
    assert registry_entry_for_module(out, "nsx-sensors").revision == _PIN
    # Non-revision module fields survive propagation untouched.
    assert out["modules"]["nsx-sensors"]["metadata"] == "modules/nsx-sensors/nsx-module.yaml"


def test_app_project_pin_leaves_other_projects_modules_alone() -> None:
    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["other-mod"]["revision"] == "v3.0.0"


def test_same_source_module_pin_beats_its_own_project_pin() -> None:
    """Within one source, a module-level pin outranks the project pin.

    Starter-profile emissions (and monorepo per-module pins) write both a
    project pin and explicit module pins into the same app block; the module
    pins must keep winning.
    """

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
            "modules": {"nsx-sensors": {"revision": "module-pin"}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == "module-pin"
    assert out["projects"]["nsx-sensors"]["revision"] == _PIN


def test_no_app_overrides_keeps_packaged_behavior() -> None:
    out = _effective_registry(_sensors_base_registry(), {})
    assert out["modules"]["nsx-sensors"]["revision"] == "v0.1.0"
    assert out["projects"]["nsx-sensors"]["revision"] == "v0.1.0"


def test_layer_project_pin_propagates_to_modules() -> None:
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-sensors": {"revision": "bringup/branch"}}}},
            ]
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == "bringup/branch"


def test_higher_layer_project_pin_beats_lower_layer_module_pin() -> None:
    """Across sources, the higher-precedence project pin wins."""

    nsx_cfg = {
        "registry": {
            "layers": [
                {
                    "inline": {
                        "modules": {
                            "nsx-sensors": {"project": "nsx-sensors", "revision": "layer-module"}
                        }
                    }
                },
            ]
        },
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
        },
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == _PIN


def test_module_pin_in_later_layer_beats_earlier_project_pin() -> None:
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-sensors": {"revision": "layer-project"}}}},
                {"inline": {"modules": {"nsx-sensors": {"revision": "later-module"}}}},
            ]
        },
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == "later-module"


def test_synthetic_profile_project_pin_does_not_propagate() -> None:
    """Profile defaults are packaged-derived: same source, no propagation.

    A family baseline expresses its module intent through explicit
    ``module_overrides``; its project pin must not repin modules the family
    deliberately left at their base-registry revisions.
    """

    nsx_cfg = {
        "_profile_registry": {
            "projects": {"nsx-sensors": {"revision": "family-rev"}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["projects"]["nsx-sensors"]["revision"] == "family-rev"
    assert out["modules"]["nsx-sensors"]["revision"] == "v0.1.0"


def test_project_override_without_revision_does_not_touch_modules(tmp_path: Path) -> None:
    """A ``local_path``-only project override expresses no revision opinion."""

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"local_path": str(tmp_path)}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == "v0.1.0"


def test_empty_module_revision_in_same_layer_does_not_block_propagation() -> None:
    """A same-layer module override with an empty revision has no opinion."""

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
            "modules": {"nsx-sensors": {"metadata": "modules/nsx-sensors/nsx-module.yaml"}},
        }
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == _PIN


# --- module/project alignment guard (partial-migration detection) ---------


def _bundle_base_registry() -> dict:
    """Base registry where the SDK module still points at the unified monorepo."""

    return {
        "projects": {
            "nsx-ambiq-bsp": {"name": "nsx-ambiq-bsp", "revision": "v0.1.0"},
            "nsx-ambiq-sdk": {"name": "nsx-ambiq-sdk", "revision": "main"},
        },
        "modules": {
            "nsx-ambiq-bsp": {
                "project": "nsx-ambiq-bsp",
                "revision": "v0.1.0",
                "metadata": "nsx-module.yaml",
            },
        },
    }


def test_alignment_passes_when_module_override_present() -> None:
    """A module whose override moves it onto the bundle project aligns."""

    base = _bundle_base_registry()
    nsx_cfg = {
        "modules": [
            {"name": "nsx-ambiq-bsp", "project": "nsx-ambiq-sdk"},
        ],
        "module_registry": {
            "projects": {"nsx-ambiq-sdk": {"revision": "main"}},
            "modules": {
                "nsx-ambiq-bsp": {
                    "project": "nsx-ambiq-sdk",
                    "revision": "main",
                    "metadata": "modules/nsx-ambiq-bsp/nsx-module.yaml",
                },
            },
        },
    }
    registry = _effective_registry(base, nsx_cfg)
    # Should not raise.
    validate_app_module_alignment(nsx_cfg, registry)


def test_alignment_detects_partial_migration() -> None:
    """A module pinned to the bundle but missing its override is rejected."""

    base = _bundle_base_registry()
    nsx_cfg = {
        "modules": [
            {"name": "nsx-ambiq-bsp", "project": "nsx-ambiq-sdk"},
        ],
        "module_registry": {
            "projects": {"nsx-ambiq-sdk": {"revision": "main"}},
            # NOTE: no modules override for nsx-ambiq-bsp — the partial
            # migration that broke the examples.
        },
    }
    registry = _effective_registry(base, nsx_cfg)
    with pytest.raises(NSXConfigError) as exc:
        validate_app_module_alignment(nsx_cfg, registry)
    msg = str(exc.value)
    assert "nsx-ambiq-bsp" in msg
    assert "nsx-ambiq-sdk" in msg
    assert "nsx-ambiq-bsp" in msg  # the stale resolved project name


def test_alignment_ignores_modules_without_declared_project() -> None:
    base = _bundle_base_registry()
    nsx_cfg = {"modules": [{"name": "nsx-ambiq-bsp"}]}
    registry = _effective_registry(base, nsx_cfg)
    validate_app_module_alignment(nsx_cfg, registry)


def test_alignment_ignores_local_and_vendored_modules() -> None:
    base = _bundle_base_registry()
    nsx_cfg = {
        "modules": [
            {"name": "my-local", "project": "nsx-ambiq-sdk", "local": True},
            {
                "name": "my-vendored",
                "project": "nsx-ambiq-sdk",
                "source": {"vendored": True},
            },
        ]
    }
    registry = _effective_registry(base, nsx_cfg)
    validate_app_module_alignment(nsx_cfg, registry)
