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
    assert out["projects"]["nsx-core"]["local_path"] == "../../shared/nsx-core"
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


# --- module/project alignment guard (partial-migration detection) ---------


def _bundle_base_registry() -> dict:
    """Base registry where the SDK module still points at the unified monorepo."""

    return {
        "projects": {
            "nsx-ambiq-bsp-r5": {"name": "nsx-ambiq-bsp-r5", "revision": "v0.1.0"},
            "nsx-ambiq-sdk": {"name": "nsx-ambiq-sdk", "revision": "main"},
        },
        "modules": {
            "nsx-ambiq-bsp-r5": {
                "project": "nsx-ambiq-bsp-r5",
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
            {"name": "nsx-ambiq-bsp-r5", "project": "nsx-ambiq-sdk"},
        ],
        "module_registry": {
            "projects": {"nsx-ambiq-sdk": {"revision": "main"}},
            "modules": {
                "nsx-ambiq-bsp-r5": {
                    "project": "nsx-ambiq-sdk",
                    "revision": "main",
                    "metadata": "modules/nsx-ambiq-bsp-r5/nsx-module.yaml",
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
            {"name": "nsx-ambiq-bsp-r5", "project": "nsx-ambiq-sdk"},
        ],
        "module_registry": {
            "projects": {"nsx-ambiq-sdk": {"revision": "main"}},
            # NOTE: no modules override for nsx-ambiq-bsp-r5 — the partial
            # migration that broke the examples.
        },
    }
    registry = _effective_registry(base, nsx_cfg)
    with pytest.raises(NSXConfigError) as exc:
        validate_app_module_alignment(nsx_cfg, registry)
    msg = str(exc.value)
    assert "nsx-ambiq-bsp-r5" in msg
    assert "nsx-ambiq-sdk" in msg
    assert "nsx-ambiq-bsp-r5" in msg  # the stale resolved project name


def test_alignment_ignores_modules_without_declared_project() -> None:
    base = _bundle_base_registry()
    nsx_cfg = {"modules": [{"name": "nsx-ambiq-bsp-r5"}]}
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
