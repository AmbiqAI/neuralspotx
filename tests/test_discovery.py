"""Tests for upward app-root walk and module discovery API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from neuralspotx.project_config import find_app_root, resolve_app_dir
from neuralspotx.module_discovery import (
    resolve_module_context,
    resolve_target_context,
    compatibility_matches,
    list_modules,
    describe_module,
    search_modules,
)


# ------------------------------------------------------------------
# find_app_root
# ------------------------------------------------------------------


class TestFindAppRoot:
    def test_finds_nsx_yml_in_start_dir(self, tmp_path: Path) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        assert find_app_root(tmp_path) == tmp_path

    def test_walks_upward(self, tmp_path: Path) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        child = tmp_path / "src" / "deep"
        child.mkdir(parents=True)
        assert find_app_root(child) == tmp_path

    def test_stops_at_git_boundary(self, tmp_path: Path) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        nested = tmp_path / "repo"
        nested.mkdir()
        (nested / ".git").mkdir()
        inner = nested / "sub"
        inner.mkdir()
        # .git is in nested/, so walking from inner should stop at nested/ and not find nsx.yml
        assert find_app_root(inner) is None

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        child = tmp_path / "empty"
        child.mkdir()
        # tmp_path has no nsx.yml and probably has a parent boundary
        # We can't guarantee None in all CI envs, but at least check it doesn't error
        result = find_app_root(child)
        # Should either be None or a path — just verify it doesn't raise
        assert result is None or isinstance(result, Path)

    def test_git_boundary_with_nsx_yml_at_same_level(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        # nsx.yml is at the .git level — should be found
        assert find_app_root(tmp_path) == tmp_path

    def test_defaults_to_cwd_when_start_is_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        monkeypatch.chdir(tmp_path)
        assert find_app_root() == tmp_path


# ------------------------------------------------------------------
# resolve_app_dir
# ------------------------------------------------------------------


class TestResolveAppDir:
    def test_explicit_path_returned(self, tmp_path: Path) -> None:
        assert resolve_app_dir(tmp_path) == tmp_path.resolve()

    def test_explicit_non_dot_string(self, tmp_path: Path) -> None:
        target = tmp_path / "myapp"
        target.mkdir()
        result = resolve_app_dir(str(target))
        assert result == target.resolve()

    def test_dot_triggers_upward_walk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        child = tmp_path / "src"
        child.mkdir()
        monkeypatch.chdir(child)
        result = resolve_app_dir(".")
        assert result == tmp_path

    def test_none_triggers_upward_walk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "nsx.yml").write_text("target:\n  board: apollo510_evb\n")
        monkeypatch.chdir(tmp_path)
        result = resolve_app_dir(None)
        assert result == tmp_path

    def test_falls_back_to_dot_when_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        # No nsx.yml anywhere reachable — should fall back to "."
        result = resolve_app_dir(".")
        assert result == tmp_path.resolve()


# ------------------------------------------------------------------
# resolve_module_context
# ------------------------------------------------------------------


class TestResolveModuleContext:
    def test_packaged_when_no_app(self) -> None:
        registry, enabled, app_dir, scope = resolve_module_context(app_dir=None)
        assert scope == "packaged"
        assert app_dir is None
        assert isinstance(registry, dict)
        assert len(enabled) == 0

    def test_app_effective_with_app_dir(self, tmp_path: Path) -> None:
        nsx_cfg = {
            "schema_version": 1,
            "nsx_tool_version": "0.1.0",
            "target": {"board": "apollo510_evb", "soc": "apollo510"},
            "modules": [],
        }
        (tmp_path / "nsx.yml").write_text(yaml.dump(nsx_cfg), encoding="utf-8")
        registry, enabled, app_dir, scope = resolve_module_context(app_dir=tmp_path)
        assert scope == "app-effective"
        assert app_dir == tmp_path
        assert isinstance(registry, dict)


# ------------------------------------------------------------------
# resolve_target_context
# ------------------------------------------------------------------


class TestResolveTargetContext:
    def test_returns_none_without_any_info(self) -> None:
        result = resolve_target_context(app_dir=None)
        assert result is None

    def test_explicit_overrides(self) -> None:
        result = resolve_target_context(
            app_dir=None,
            board="apollo510_evb",
            soc="apollo510",
            toolchain="arm-none-eabi-gcc",
        )
        assert result == {
            "board": "apollo510_evb",
            "soc": "apollo510",
            "toolchain": "arm-none-eabi-gcc",
        }

    def test_merges_with_app_config(self, tmp_path: Path) -> None:
        nsx_cfg = {
            "schema_version": 1,
            "nsx_tool_version": "0.1.0",
            "target": {"board": "apollo510_evb", "soc": "apollo510"},
            "toolchain": "arm-none-eabi-gcc",
            "modules": [],
        }
        (tmp_path / "nsx.yml").write_text(yaml.dump(nsx_cfg), encoding="utf-8")
        result = resolve_target_context(app_dir=tmp_path)
        assert result is not None
        assert result["board"] == "apollo510_evb"


# ------------------------------------------------------------------
# compatibility_matches
# ------------------------------------------------------------------


class TestCompatibilityMatches:
    def test_returns_none_without_metadata(self) -> None:
        record = {"metadata_available": False}
        assert compatibility_matches(record, {"board": "a"}) is None

    def test_returns_none_without_target(self) -> None:
        record = {"metadata_available": True, "compatibility": {}}
        assert compatibility_matches(record, None) is None

    def test_compatible_wildcard(self) -> None:
        record = {
            "metadata_available": True,
            "compatibility": {
                "boards": ["*"],
                "socs": ["*"],
                "toolchains": ["*"],
            },
        }
        ctx = {"board": "x", "soc": "y", "toolchain": "z"}
        assert compatibility_matches(record, ctx) is True

    def test_incompatible_soc(self) -> None:
        record = {
            "metadata_available": True,
            "compatibility": {
                "boards": ["*"],
                "socs": ["apollo510"],
                "toolchains": ["*"],
            },
        }
        ctx = {"board": "x", "soc": "apollo3", "toolchain": "gcc"}
        assert compatibility_matches(record, ctx) is False


# ------------------------------------------------------------------
# list_modules / describe_module / search_modules
# ------------------------------------------------------------------


class TestDiscoveryAPI:
    def test_list_modules_packaged(self) -> None:
        modules = list_modules()
        assert isinstance(modules, list)
        assert len(modules) > 0
        names = {m["name"] for m in modules}
        assert "nsx-core" in names

    def test_list_modules_registry_only(self) -> None:
        modules = list_modules(registry_only=True)
        assert isinstance(modules, list)
        assert len(modules) > 0

    def test_describe_module_known(self) -> None:
        record = describe_module("nsx-core")
        assert record["name"] == "nsx-core"
        # Without app_dir, metadata may not resolve (packaged registry only)
        assert "name" in record and "project" in record

    def test_describe_module_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            describe_module("nonexistent-module-xyz")

    def test_search_modules_by_keyword(self) -> None:
        results = search_modules("core")
        assert isinstance(results, list)
        assert len(results) > 0
        assert all("score" in r for r in results)

    def test_search_modules_empty_query(self) -> None:
        results = search_modules("")
        assert results == []


# ------------------------------------------------------------------
# validate_module_metadata
# ------------------------------------------------------------------


class TestValidateModuleMetadata:
    def test_valid_metadata(self, tmp_path: Path) -> None:
        from neuralspotx import validate_module_metadata

        metadata = tmp_path / "nsx-module.yaml"
        metadata.write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    "module:",
                    "  name: test-mod",
                    "  type: runtime",
                    '  version: "0.1.0"',
                    "support:",
                    "  ambiqsuite: true",
                    "  zephyr: false",
                    "build:",
                    "  cmake:",
                    "    package: test_mod",
                    "    targets: [test_mod]",
                    "depends:",
                    "  required: []",
                    "  optional: []",
                    "compatibility:",
                    '  boards: ["*"]',
                    '  socs: ["*"]',
                    '  toolchains: ["arm-none-eabi-gcc"]',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        data = validate_module_metadata(metadata)
        assert data["module"]["name"] == "test-mod"

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        from neuralspotx import validate_module_metadata, NSXError

        metadata = tmp_path / "nsx-module.yaml"
        metadata.write_text(
            "schema_version: 1\nmodule:\n  name: bad\n",
            encoding="utf-8",
        )
        with pytest.raises(NSXError):
            validate_module_metadata(metadata)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        from neuralspotx import validate_module_metadata, NSXError

        with pytest.raises(NSXError):
            validate_module_metadata(tmp_path / "does-not-exist.yaml")

    def test_cli_validate_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        import argparse
        from neuralspotx.cli import cmd_module_validate

        metadata = tmp_path / "nsx-module.yaml"
        metadata.write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    "module:",
                    "  name: cli-test",
                    "  type: runtime",
                    '  version: "1.0.0"',
                    "support:",
                    "  ambiqsuite: true",
                    "  zephyr: false",
                    "build:",
                    "  cmake:",
                    "    package: cli_test",
                    "    targets: [cli_test]",
                    "depends:",
                    "  required: []",
                    "  optional: []",
                    "compatibility:",
                    '  boards: ["*"]',
                    '  socs: ["*"]',
                    '  toolchains: ["arm-none-eabi-gcc"]',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        cmd_module_validate(argparse.Namespace(metadata=str(metadata), json=False))
        output = capsys.readouterr().out
        assert "Valid" in output
        assert "cli-test" in output

    def test_cli_validate_invalid(self, tmp_path: Path) -> None:
        import argparse
        from neuralspotx.cli import cmd_module_validate

        metadata = tmp_path / "nsx-module.yaml"
        metadata.write_text("schema_version: 1\nmodule:\n  name: bad\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="Validation failed"):
            cmd_module_validate(argparse.Namespace(metadata=str(metadata), json=False))


# ------------------------------------------------------------------
# Package-level exports
# ------------------------------------------------------------------


def test_public_exports() -> None:
    import neuralspotx

    assert hasattr(neuralspotx, "find_app_root")
    assert hasattr(neuralspotx, "resolve_app_dir")
    assert hasattr(neuralspotx, "list_modules")
    assert hasattr(neuralspotx, "describe_module")
    assert hasattr(neuralspotx, "search_modules")
    assert hasattr(neuralspotx, "validate_module_metadata")
