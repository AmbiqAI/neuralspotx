"""Phase 3 — typed `nsx.yml` loader (`NsxProject`).

These tests exercise the strict structural validation performed by
`NsxProject.from_yaml` / `NsxProject.from_mapping` and the round-trip
property of `NsxProject.to_yaml`. They cover:

  * The minimum-viable manifest parses cleanly and exposes typed
    accessors.
  * At least six distinct invalid manifest shapes each raise an
    `NSXConfigError` whose `.field` names the offending YAML key
    path (per Issue #64 acceptance criteria).
  * Round-trip: loading, re-emitting, and reloading produces an
    equivalent typed instance (modulo formatting).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from neuralspotx import NSXConfigError
from neuralspotx.models import NsxProject

_MIN_CFG: dict[str, object] = {
    "schema_version": 1,
    "project": {"name": "testapp"},
    "target": {"board": "apollo510_evb", "soc": "apollo510"},
    "toolchain": "arm-none-eabi-gcc",
    "modules": [],
}


def _write(tmp_path: Path, cfg: object) -> Path:
    path = tmp_path / "nsx.yml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestLoadHappy:
    def test_minimum_manifest_parses(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _MIN_CFG)
        project = NsxProject.from_yaml(path)
        assert project.schema_version == 1
        assert project.project_name == "testapp"
        assert project.board == "apollo510_evb"
        assert project.toolchain == "arm-none-eabi-gcc"
        assert project.modules == ()
        assert project.path == path

    def test_modules_are_typed(self, tmp_path: Path) -> None:
        cfg = dict(_MIN_CFG)
        cfg["modules"] = [
            {"name": "m1"},
            {"name": "m2", "source": {"vendored": True}},
        ]
        path = _write(tmp_path, cfg)
        project = NsxProject.from_yaml(path)
        assert tuple(m.name for m in project.modules) == ("m1", "m2")
        assert project.modules[1].is_vendored

    def test_app_config_view_round_trip(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _MIN_CFG)
        project = NsxProject.from_yaml(path)
        legacy = project.app_config()
        assert legacy.project_name == "testapp"


# ---------------------------------------------------------------------------
# Invalid manifest shapes (acceptance: ≥6, each producing NSXConfigError
# with `.field` populated).
# ---------------------------------------------------------------------------


_INVALID_SHAPES: list[tuple[str, dict[str, object] | object, str]] = [
    (
        "missing-schema-version",
        {
            "project": {"name": "a"},
            "target": {},
            "modules": [],
        },
        "schema_version",
    ),
    (
        "schema-version-wrong-type",
        {
            "schema_version": "1",
            "project": {"name": "a"},
            "target": {},
            "modules": [],
        },
        "schema_version",
    ),
    (
        "unsupported-schema-version",
        {
            "schema_version": 99,
            "project": {"name": "a"},
            "target": {},
            "modules": [],
        },
        "schema_version",
    ),
    (
        "project-not-mapping",
        {
            "schema_version": 1,
            "project": "testapp",
            "target": {},
            "modules": [],
        },
        "project",
    ),
    (
        "project-name-missing",
        {
            "schema_version": 1,
            "project": {},
            "target": {},
            "modules": [],
        },
        "project.name",
    ),
    (
        "project-name-empty",
        {
            "schema_version": 1,
            "project": {"name": ""},
            "target": {},
            "modules": [],
        },
        "project.name",
    ),
    (
        "target-not-mapping",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": "apollo510_evb",
            "modules": [],
        },
        "target",
    ),
    (
        "target-board-wrong-type",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {"board": 42},
            "modules": [],
        },
        "target.board",
    ),
    (
        "toolchain-wrong-type",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "toolchain": ["gcc"],
            "modules": [],
        },
        "toolchain",
    ),
    (
        "modules-not-list",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": {"name": "m1"},
        },
        "modules",
    ),
    (
        "module-entry-not-mapping",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": ["m1"],
        },
        "modules[0]",
    ),
    (
        "module-name-missing",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": [{"project": "p"}],
        },
        "modules[0].name",
    ),
    (
        "module-registry-not-mapping",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": [],
            "module_registry": [],
        },
        "module_registry",
    ),
    (
        "tooling-not-mapping",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": [],
            "tooling": "v1",
        },
        "tooling",
    ),
    (
        "profile-wrong-type",
        {
            "schema_version": 1,
            "project": {"name": "a"},
            "target": {},
            "modules": [],
            "profile": 5,
        },
        "profile",
    ),
]


@pytest.mark.parametrize(("label", "cfg", "expected_field"), _INVALID_SHAPES)
def test_invalid_manifest_raises_with_field(
    tmp_path: Path,
    label: str,
    cfg: object,
    expected_field: str,
) -> None:
    path = _write(tmp_path, cfg)
    with pytest.raises(NSXConfigError) as exc_info:
        NsxProject.from_yaml(path)
    assert exc_info.value.field == expected_field, (
        f"[{label}] expected .field={expected_field!r}, "
        f"got {exc_info.value.field!r} from message: {exc_info.value}"
    )


# ---------------------------------------------------------------------------
# Other validation surfaces
# ---------------------------------------------------------------------------


class TestNonStructuralFailures:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(NSXConfigError, match="not found"):
            NsxProject.from_yaml(tmp_path / "missing.yml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("foo: : :\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="invalid YAML"):
            NsxProject.from_yaml(path)

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("# only a comment\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="empty"):
            NsxProject.from_yaml(path)

    def test_root_not_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="mapping at the root"):
            NsxProject.from_yaml(path)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_to_yaml_then_from_yaml_is_equivalent(self, tmp_path: Path) -> None:
        cfg = dict(_MIN_CFG)
        cfg["modules"] = [
            {"name": "m1", "revision": "v1.0"},
            {"name": "m2", "source": {"vendored": True}},
        ]
        cfg["module_registry"] = {"projects": {"p": {"url": "https://example/p.git"}}}
        cfg["tooling"] = {"nsx": {"version": "0.9.0", "major": 0}}
        cfg["profile"] = "starter"
        cfg["profile_status"] = "active"

        path = _write(tmp_path, cfg)
        project = NsxProject.from_yaml(path)

        out_path = tmp_path / "nsx-roundtrip.yml"
        project.to_yaml(out_path)
        reloaded = NsxProject.from_yaml(out_path)

        # to_mapping() captures the canonical dict view; equality across
        # round-trip is the round-trip property the issue requires.
        assert reloaded.to_mapping() == project.to_mapping()
        assert reloaded.project_name == project.project_name
        assert tuple(m.name for m in reloaded.modules) == tuple(m.name for m in project.modules)

    def test_to_yaml_returns_text_when_no_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _MIN_CFG)
        project = NsxProject.from_yaml(path)
        text = project.to_yaml(None)
        assert "schema_version: 1" in text
        assert "project:" in text


# ---------------------------------------------------------------------------
# Forward-compat: unknown top-level keys are preserved verbatim.
# ---------------------------------------------------------------------------


class TestForwardCompat:
    def test_unknown_top_level_key_is_preserved(self, tmp_path: Path) -> None:
        cfg = dict(_MIN_CFG)
        cfg["future_key"] = {"reserved": True}
        path = _write(tmp_path, cfg)
        project = NsxProject.from_yaml(path)
        assert project.extra == {"future_key": {"reserved": True}}
        assert project.to_mapping()["future_key"] == {"reserved": True}
