"""Tests for M4 — typed exceptions backed by ``SystemExit`` multi-inheritance.

These tests pin the contract that:

1. ``NSXError`` IS-A both :class:`SystemExit` and :class:`RuntimeError`,
   so existing ``except SystemExit:`` handlers (CLI wrapper, prior tests,
   third-party embedders) continue to catch typed errors unchanged.
2. The migrated raise sites in ``tooling``, ``project_config``,
   ``module_registry`` and ``subprocess_utils`` raise the *typed*
   subclass, not bare ``SystemExit``.
3. ``SystemExit.code`` is populated from the message argument so legacy
   ``exc.code`` consumers keep working.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neuralspotx import (
    NSXConfigError,
    NSXError,
    NSXLockError,
    NSXModuleError,
    NSXResolutionError,
    NSXTimeoutError,
    NSXToolchainError,
    project_config,
    tooling,
)
from neuralspotx.subprocess_utils import extract_view_command

_ALL_ERRORS = (
    NSXError,
    NSXTimeoutError,
    NSXConfigError,
    NSXResolutionError,
    NSXLockError,
    NSXModuleError,
    NSXToolchainError,
)


class TestHierarchy:
    @pytest.mark.parametrize("cls", _ALL_ERRORS)
    def test_is_systemexit_and_runtimeerror(self, cls):
        assert issubclass(cls, SystemExit)
        assert issubclass(cls, RuntimeError)

    @pytest.mark.parametrize("cls", _ALL_ERRORS)
    def test_legacy_systemexit_handler_still_catches(self, cls):
        """Pre-M4 ``except SystemExit:`` handlers must keep working."""
        if cls is NSXTimeoutError:
            instance = cls("msg")
        else:
            instance = cls("msg")

        with pytest.raises(SystemExit):
            raise instance

    def test_code_attribute_populated_from_message(self):
        # SystemExit semantics: first positional arg becomes ``code``.
        # Embedders that rely on ``exc.code`` must keep working.
        assert NSXLockError("lock busy").code == "lock busy"
        assert NSXConfigError("bad yaml").code == "bad yaml"


class TestMigratedSites:
    def test_tooling_missing_tool_raises_toolchain_error(self):
        with pytest.raises(NSXToolchainError, match="not found in PATH"):
            tooling.require_tool("nsx-definitely-not-a-real-binary-xyz")

    def test_project_config_missing_app_raises_config_error(self, tmp_path):
        with pytest.raises(NSXConfigError, match="not found"):
            project_config._require_app_config(tmp_path)

    def test_project_config_invalid_yaml_raises_config_error(self, tmp_path):
        path = tmp_path / "nsx.yml"
        path.write_text(": : not yaml :\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="invalid YAML"):
            project_config._read_yaml(path)

    def test_project_config_empty_yaml_raises_config_error(self, tmp_path):
        path = tmp_path / "nsx.yml"
        path.write_text("# only a comment\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="empty or contains only comments"):
            project_config._read_yaml(path)

    def test_subprocess_utils_missing_ninja_raises_config_error(self, tmp_path):
        with pytest.raises(NSXConfigError, match="Missing build.ninja"):
            extract_view_command(tmp_path, target="anything")


class TestDualCatchability:
    """Each migrated site is catchable as both the typed class AND ``SystemExit``."""

    def test_toolchain_error_dual_catch(self):
        with pytest.raises(NSXToolchainError):
            tooling.require_tool("nsx-definitely-not-a-real-binary-xyz")
        with pytest.raises(SystemExit):
            tooling.require_tool("nsx-definitely-not-a-real-binary-xyz")

    def test_config_error_dual_catch(self, tmp_path: Path):
        with pytest.raises(NSXConfigError):
            project_config._require_app_config(tmp_path)
        with pytest.raises(SystemExit):
            project_config._require_app_config(tmp_path)
