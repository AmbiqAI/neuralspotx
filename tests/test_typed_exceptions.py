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
    operations,
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

    # ----- operations.py migrated sites -----

    def test_operations_create_app_missing_soc_raises_config_error(self, tmp_path):
        # Board "unknown" has no default SoC mapping → NSXConfigError.
        with pytest.raises(NSXConfigError, match="Unable to infer --soc"):
            operations.create_app_impl(
                tmp_path / "myapp",
                board="not-a-real-board",
                soc=None,
                force=False,
                no_bootstrap=True,
            )

    def test_operations_init_module_empty_name_raises_module_error(self, tmp_path):
        with pytest.raises(NSXModuleError, match="Module name must not be empty"):
            operations.init_module_impl(
                tmp_path,
                module_name="   ",
                force=True,
            )

    def test_operations_outdated_missing_lock_raises_config_error(self, tmp_path):
        # nsx.yml exists but no nsx.lock → NSXConfigError.
        (tmp_path / "nsx.yml").write_text(
            "app:\n  name: t\n  board: apollo510_evb\n  soc: apollo510\nmodules: []\n",
            encoding="utf-8",
        )
        with pytest.raises(NSXConfigError, match="nsx.lock.*not found"):
            operations.outdated_app_impl(tmp_path)

    def test_operations_sync_frozen_missing_lock_raises_config_error(self, tmp_path):
        (tmp_path / "nsx.yml").write_text(
            "app:\n  name: t\n  board: apollo510_evb\n  soc: apollo510\nmodules: []\n",
            encoding="utf-8",
        )
        with pytest.raises(NSXConfigError, match="nsx.lock.*not found"):
            operations.sync_app_impl(tmp_path, frozen=True)

    # ----- cli.py migrated sites -----

    def test_cli_module_list_without_app_dir_raises_config_error(self):
        from neuralspotx import cli

        ns = type(
            "Args",
            (),
            {"app_dir": None, "registry_only": False, "json": False},
        )()
        with pytest.raises(NSXConfigError, match="requires --app-dir"):
            cli.cmd_module_list(ns)

    def test_cli_module_validate_invalid_yaml_raises_config_error(self, tmp_path):
        from neuralspotx import cli

        bad = tmp_path / "nsx-module.yaml"
        bad.write_text(": : not yaml :\n", encoding="utf-8")
        ns = type("Args", (), {"metadata": str(bad), "json": False})()
        with pytest.raises(NSXConfigError):
            cli.cmd_module_validate(ns)


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
