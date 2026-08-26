"""Tests for layered registry resolution (``registry.layers`` in nsx.yml)."""

from __future__ import annotations

import contextlib
import copy
import logging
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.project_config import (
    _effective_registry,
    _reset_pin_stomp_warnings,
    validate_app_module_alignment,
)


@pytest.fixture(autouse=True)
def _fresh_stomp_warning_state() -> Iterator[None]:
    """Isolate the process-wide stomp-warning dedup registry per test."""

    _reset_pin_stomp_warnings()
    yield
    _reset_pin_stomp_warnings()


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
    """Packaged-shaped base: project and module both at one packaged default.

    Synthetic registry frozen for these precedence scenarios — the v0.1.0 /
    v3.0.0 values are fixture constants, not a mirror of the live packaged
    ``registry.lock.yaml`` (whose nsx-sensors entry moves independently).
    """

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


_PROJECT_CONFIG_LOGGER = "neuralspotx.project_config"


class _WarningRecorder(logging.Handler):
    """Collects records emitted on the ``project_config`` logger."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@contextlib.contextmanager
def _recorded_warnings() -> Iterator[_WarningRecorder]:
    """Capture warnings directly on the module logger.

    The CLI's ``configure_logging`` sets ``propagate = False`` on the
    ``neuralspotx`` root logger (and may raise its level), so root-level
    capture (``caplog``) misses these records once any CLI test has run.
    Attaching the handler to the emitting logger itself is order-immune.
    """

    logger = logging.getLogger(_PROJECT_CONFIG_LOGGER)
    recorder = _WarningRecorder()
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(recorder)
    try:
        yield recorder
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(old_level)


def test_later_layer_project_pin_stomp_over_earlier_module_pin_warns() -> None:
    """A cross-layer stomp of an explicit module pin is loud.

    A bring-up overlay pins one module's revision; the manifest's
    ``module_registry`` block (a *later* app-authored layer) pins the whole
    project. Layer precedence wins — the project pin repins the module — but
    a specific pin losing to a general one must be diagnosed, not silent.
    """

    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"modules": {"nsx-sensors": {"revision": "fix/ble-crash"}}}},
            ]
        },
        "module_registry": {"projects": {"nsx-sensors": {"revision": _PIN}}},
    }
    with _recorded_warnings() as recorder:
        out = _effective_registry(_sensors_base_registry(), nsx_cfg)

    assert out["modules"]["nsx-sensors"]["revision"] == _PIN
    stomps = [r for r in recorder.records if "pinned module-level" in r.getMessage()]
    assert len(stomps) == 1
    message = stomps[0].getMessage()
    assert "nsx-sensors" in message
    assert "fix/ble-crash" in message
    assert _PIN in message
    assert "module_registry" in message


def test_packaged_default_propagation_does_not_warn() -> None:
    """Overriding a packaged/profile-sourced module revision is silent.

    That overwrite is the fix working as intended; only explicit
    app-authored module pins earn a stomp warning.
    """

    nsx_cfg = {
        "_profile_registry": {
            "modules": {"nsx-sensors": {"revision": "family-module-rev"}},
        },
        "module_registry": {"projects": {"nsx-sensors": {"revision": _PIN}}},
    }
    with _recorded_warnings() as recorder:
        out = _effective_registry(_sensors_base_registry(), nsx_cfg)

    assert out["modules"]["nsx-sensors"]["revision"] == _PIN
    assert not [r for r in recorder.records if "pinned module-level" in r.getMessage()]


def test_stomp_warning_dedups_recomputations_but_not_new_stomps() -> None:
    """A given stomp warns once per process; a different stomp still warns.

    ``_effective_registry`` is recomputed at many call sites per command, so
    an identical (module, old, new, layer) stomp must not repeat — while any
    genuinely new stomp must never be suppressed.
    """

    stomp_a: dict[str, Any] = {
        "registry": {
            "layers": [
                {"inline": {"modules": {"nsx-sensors": {"revision": "overlay-a"}}}},
            ]
        },
        "module_registry": {"projects": {"nsx-sensors": {"revision": _PIN}}},
    }
    # Same module and winning pin, different earlier revision -> distinct stomp.
    stomp_b = copy.deepcopy(stomp_a)
    stomp_b["registry"]["layers"][0]["inline"]["modules"]["nsx-sensors"]["revision"] = "overlay-b"

    def _stomps(records: list[logging.LogRecord]) -> list[str]:
        return [r.getMessage() for r in records if "pinned module-level" in r.getMessage()]

    with _recorded_warnings() as recorder:
        _effective_registry(_sensors_base_registry(), stomp_a)
        _effective_registry(_sensors_base_registry(), stomp_a)  # recomputation
        _effective_registry(_sensors_base_registry(), stomp_a)  # recomputation
    assert len(_stomps(recorder.records)) == 1

    with _recorded_warnings() as recorder:
        _effective_registry(_sensors_base_registry(), stomp_b)
    messages = _stomps(recorder.records)
    assert len(messages) == 1
    assert "overlay-b" in messages[0]


def test_stomp_warning_quotes_pin_erased_by_same_layer() -> None:
    """The warning quotes the true earlier pin even after a same-layer erasure.

    A later layer that both blanks the module's revision (``revision: ""``)
    and pins the project would otherwise leave ``''`` as the "earlier pinned"
    value by the time propagation compares — the provenance map keeps the
    real value.
    """

    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"modules": {"nsx-sensors": {"revision": "fix/old-pin"}}}},
            ]
        },
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": _PIN}},
            "modules": {"nsx-sensors": {"revision": ""}},
        },
    }
    with _recorded_warnings() as recorder:
        out = _effective_registry(_sensors_base_registry(), nsx_cfg)

    assert out["modules"]["nsx-sensors"]["revision"] == _PIN
    stomps = [r.getMessage() for r in recorder.records if "pinned module-level" in r.getMessage()]
    assert len(stomps) == 1
    assert "'fix/old-pin'" in stomps[0]
    assert "''" not in stomps[0]


def test_repoint_without_revision_drops_propagated_pin() -> None:
    """A propagated pin is project-scoped: it does not survive a re-point.

    An earlier layer's project pin propagates onto the module; a later layer
    that re-points the module to a different project without expressing a
    revision falls back to the value propagation had replaced, instead of
    leaking the old project's pin onto the new project.
    """

    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-sensors": {"revision": "old-project-pin"}}}},
            ]
        },
        "module_registry": {
            "modules": {"nsx-sensors": {"project": "other-proj"}},
        },
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["project"] == "other-proj"
    assert out["modules"]["nsx-sensors"]["revision"] == "v0.1.0"


def test_repoint_with_same_layer_project_pin_follows_new_project() -> None:
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-sensors": {"revision": "old-project-pin"}}}},
            ]
        },
        "module_registry": {
            "projects": {"other-proj": {"revision": "new-project-pin"}},
            "modules": {"nsx-sensors": {"project": "other-proj"}},
        },
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["project"] == "other-proj"
    assert out["modules"]["nsx-sensors"]["revision"] == "new-project-pin"


def test_repoint_keeps_explicit_module_pin() -> None:
    """Explicit module pins are module-scoped and survive a project re-point."""

    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"modules": {"nsx-sensors": {"revision": "explicit-pin"}}}},
            ]
        },
        "module_registry": {
            "modules": {"nsx-sensors": {"project": "other-proj"}},
        },
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["project"] == "other-proj"
    assert out["modules"]["nsx-sensors"]["revision"] == "explicit-pin"


def test_app_project_pin_beats_profile_synthetic_module_pin() -> None:
    """Across sources: an app-layer project pin beats a profile module pin.

    The synthetic profile defaults are packaged-derived, so an app-authored
    project pin repins even modules the profile pinned module-level.
    """

    nsx_cfg = {
        "_profile_registry": {
            "projects": {"nsx-sensors": {"revision": "family-rev"}},
            "modules": {"nsx-sensors": {"revision": "family-rev"}},
        },
        "module_registry": {"projects": {"nsx-sensors": {"revision": _PIN}}},
    }
    out = _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert out["modules"]["nsx-sensors"]["revision"] == _PIN


def test_non_string_project_revision_raises() -> None:
    """An unquoted YAML scalar project revision fails loud, not silently dead."""

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": 2024}},
        }
    }
    with pytest.raises(NSXConfigError) as exc:
        _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert "nsx-sensors" in str(exc.value)
    assert "2024" in str(exc.value)
    assert "Quote the value" in str(exc.value)
    assert exc.value.field == "module_registry.projects.nsx-sensors.revision"


def test_non_string_project_revision_in_layer_raises() -> None:
    nsx_cfg = {
        "registry": {
            "layers": [
                {"inline": {"projects": {"nsx-sensors": {"revision": 1.0}}}},
            ]
        }
    }
    with pytest.raises(NSXConfigError) as exc:
        _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert "registry.layers[0]" in str(exc.value)
    assert exc.value.field == "registry.layers[0].projects.nsx-sensors.revision"


def test_null_project_revision_gets_remove_key_remedy() -> None:
    """A bare ``revision:`` (YAML null) gets remove-the-key advice, not quoting."""

    nsx_cfg = {
        "module_registry": {
            "projects": {"nsx-sensors": {"revision": None}},
        }
    }
    with pytest.raises(NSXConfigError) as exc:
        _effective_registry(_sensors_base_registry(), nsx_cfg)
    assert "Remove the empty 'revision:' key" in str(exc.value)
    assert "Quote the value" not in str(exc.value)
    assert exc.value.field == "module_registry.projects.nsx-sensors.revision"


def test_workspace_layer_project_pin_propagates(tmp_path: Path) -> None:
    overlay = tmp_path / "bringup-registry.yaml"
    overlay.write_text(
        textwrap.dedent(
            f"""
            projects:
              nsx-sensors:
                revision: {_PIN}
            """
        ),
        encoding="utf-8",
    )
    nsx_cfg = {"registry": {"layers": [{"workspace": "bringup-registry.yaml"}]}}
    out = _effective_registry(_sensors_base_registry(), nsx_cfg, app_dir=tmp_path)
    assert out["modules"]["nsx-sensors"]["revision"] == _PIN


def test_effective_registry_is_idempotent_and_pure() -> None:
    """Same inputs, same output — and the inputs are never mutated."""

    base = _sensors_base_registry()
    nsx_cfg = {
        "_profile_registry": {
            "projects": {"other-proj": {"revision": "family-rev"}},
        },
        "registry": {
            "layers": [
                {"inline": {"modules": {"nsx-sensors": {"revision": "overlay-pin"}}}},
            ]
        },
        "module_registry": {"projects": {"nsx-sensors": {"revision": _PIN}}},
    }
    base_snapshot = copy.deepcopy(base)
    cfg_snapshot = copy.deepcopy(nsx_cfg)

    first = _effective_registry(base, nsx_cfg)
    second = _effective_registry(base, nsx_cfg)

    assert first == second
    assert base == base_snapshot
    assert nsx_cfg == cfg_snapshot


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
