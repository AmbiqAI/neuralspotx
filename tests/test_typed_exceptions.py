"""Tests for the typed-exception hierarchy.

These tests pin the contract that:

1. ``NSXError`` IS-A :class:`RuntimeError`, and every typed subclass
   (``NSXLockError``, ``NSXConfigError``, ...) IS-A ``NSXError``.
2. The migrated raise sites in ``tooling``, ``project_config``,
   ``module_registry`` and ``subprocess_utils`` raise the *typed*
   subclass.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

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
from neuralspotx.models import ModuleInitRequest
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
    def test_is_runtimeerror(self, cls):
        assert issubclass(cls, RuntimeError)
        assert not issubclass(cls, SystemExit)

    @pytest.mark.parametrize("cls", _ALL_ERRORS)
    def test_subclasses_caught_via_base(self, cls):
        with pytest.raises(NSXError):
            raise cls("msg")

    def test_message_preserved(self):
        assert str(NSXLockError("lock busy")) == "lock busy"
        assert str(NSXConfigError("bad yaml")) == "bad yaml"


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
                ModuleInitRequest(module_dir=tmp_path, module_name="   ", force=True),
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


# ---------------------------------------------------------------------------
# R20: extract_view_command resilience tests
# ---------------------------------------------------------------------------

# Realistic Ninja block templates for testing varied generator output.
_SIMPLE_NINJA = """\
build CMakeFiles/{target}.dir/dummy: phony
  pool = console
build CMakeFiles/{target}: CUSTOM_COMMAND
  COMMAND = cd /path/to/build && {cmd}
  DESC = Launching SWO viewer
  restat = 1
"""

_NO_CD_PREFIX = """\
build CMakeFiles/{target}: CUSTOM_COMMAND
  COMMAND = {cmd}
  DESC = Launching viewer
"""

_EXTRA_VARS_BEFORE_COMMAND = """\
build CMakeFiles/{target}: CUSTOM_COMMAND
  DESC = viewer
  pool = console
  depfile = CMakeFiles/{target}.d
  COMMAND = cd /build && {cmd}
  restat = 1
"""

_LEADING_WHITESPACE = """\
build CMakeFiles/{target}: CUSTOM_COMMAND
    COMMAND = cd /some/dir && {cmd}
    DESC = view
"""

_TARGET_AT_END_OF_FILE = """\
# some preamble
rule CUSTOM_COMMAND
  command = $COMMAND

build CMakeFiles/other_target: CUSTOM_COMMAND
  COMMAND = echo hello

build CMakeFiles/{target}: CUSTOM_COMMAND
  COMMAND = cd /x && {cmd}
"""

_MULTIPLE_CHAIN = """\
build CMakeFiles/{target}: CUSTOM_COMMAND
  COMMAND = cd /build && set FOO=bar && {cmd}
"""


class TestExtractViewCommandResilience:
    """R20: Cover varied Ninja generator formatting."""

    @pytest.mark.parametrize(
        "template",
        [
            _SIMPLE_NINJA,
            _NO_CD_PREFIX,
            _EXTRA_VARS_BEFORE_COMMAND,
            _LEADING_WHITESPACE,
            _TARGET_AT_END_OF_FILE,
        ],
        ids=["simple", "no-cd-prefix", "extra-vars-before", "leading-whitespace", "target-at-eof"],
    )
    def test_extracts_command_from_varied_formats(self, tmp_path, template):
        target = "myapp_view"
        cmd = "/opt/segger/JLinkSWOViewerCLExe -device AMA4B2KK -itmport 0"
        ninja = template.format(target=target, cmd=cmd)
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        assert result[0] == "/opt/segger/JLinkSWOViewerCLExe"
        assert "-device" in result
        assert "AMA4B2KK" in result

    def test_extracts_usb_serial_flag(self, tmp_path):
        target = "myapp_view"
        cmd = "/opt/segger/JLinkSWOViewerCLExe -USB 1160002204 -device AP510NFA-CBR -itmport 0"
        ninja = _NO_CD_PREFIX.format(target=target, cmd=cmd)
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        assert result[:4] == [
            "/opt/segger/JLinkSWOViewerCLExe",
            "-USB",
            "1160002204",
            "-device",
        ]

    def test_command_without_cd_chain(self, tmp_path):
        """COMMAND without && prefix returns the full command."""
        target = "app_view"
        ninja = _NO_CD_PREFIX.format(target=target, cmd="/usr/bin/viewer --port 0")
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        assert result == ["/usr/bin/viewer", "--port", "0"]

    def test_multiple_chain_takes_after_first_ampersand(self, tmp_path):
        """When COMMAND has multiple && chains, text after first && is used."""
        target = "app_view"
        ninja = _MULTIPLE_CHAIN.format(target=target, cmd="/usr/bin/viewer --arg val")
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        # "cd /build && set FOO=bar && /usr/bin/viewer --arg val"
        # After first &&: "set FOO=bar && /usr/bin/viewer --arg val"
        assert result[0] == "set"

    def test_target_not_found_raises_config_error(self, tmp_path):
        (tmp_path / "build.ninja").write_text(
            "build CMakeFiles/other: CUSTOM_COMMAND\n  COMMAND = echo hi\n",
            encoding="utf-8",
        )
        with pytest.raises(NSXConfigError, match="Unable to resolve"):
            extract_view_command(tmp_path, "nonexistent_target")

    def test_block_without_command_raises_config_error(self, tmp_path):
        """Target block exists but has no COMMAND = line within scan window."""
        target = "app_view"
        ninja = f"build CMakeFiles/{target}: CUSTOM_COMMAND\n"
        # Add 10 lines of non-COMMAND content (exceeds 7-line scan window)
        ninja += "".join(f"  VAR{i} = val{i}\n" for i in range(10))
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        with pytest.raises(NSXConfigError, match="Unable to resolve"):
            extract_view_command(tmp_path, target)

    def test_command_within_scan_window_boundary(self, tmp_path):
        """COMMAND on exactly the 7th line after header is still found."""
        target = "app_view"
        ninja = f"build CMakeFiles/{target}: CUSTOM_COMMAND\n"
        # 6 padding lines + COMMAND on 7th = lines[idx+1 : idx+8] includes it
        ninja += "".join(f"  PAD{i} = x\n" for i in range(6))
        ninja += "  COMMAND = /usr/bin/viewer\n"
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        assert result == ["/usr/bin/viewer"]

    def test_command_outside_scan_window_raises(self, tmp_path):
        """COMMAND on the 8th line after header is outside scan window."""
        target = "app_view"
        ninja = f"build CMakeFiles/{target}: CUSTOM_COMMAND\n"
        # 7 padding lines + COMMAND on 8th = lines[idx+1 : idx+8] misses it
        ninja += "".join(f"  PAD{i} = x\n" for i in range(7))
        ninja += "  COMMAND = /usr/bin/viewer\n"
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        with pytest.raises(NSXConfigError, match="Unable to resolve"):
            extract_view_command(tmp_path, target)

    def test_quoted_arguments_preserved(self, tmp_path):
        """Arguments with spaces in quotes are preserved by shlex."""
        target = "app_view"
        cmd = '/usr/bin/viewer --label "my app" --path "/some dir/file"'
        ninja = _NO_CD_PREFIX.format(target=target, cmd=cmd)
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        result = extract_view_command(tmp_path, target)
        assert result[0] == "/usr/bin/viewer"
        assert "--label" in result
        assert "--path" in result
        if os.name == "nt":
            # Windows non-POSIX shlex preserves surrounding quotes
            assert '"my app"' in result
            assert '"/some dir/file"' in result
        else:
            assert "my app" in result
            assert "/some dir/file" in result

    def test_empty_build_ninja_raises_config_error(self, tmp_path):
        (tmp_path / "build.ninja").write_text("", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="Unable to resolve"):
            extract_view_command(tmp_path, "any_target")

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
    """Each migrated site is catchable as both the typed subclass and ``NSXError``."""

    def test_toolchain_error_dual_catch(self):
        with pytest.raises(NSXToolchainError):
            tooling.require_tool("nsx-definitely-not-a-real-binary-xyz")
        with pytest.raises(NSXError):
            tooling.require_tool("nsx-definitely-not-a-real-binary-xyz")

    def test_config_error_dual_catch(self, tmp_path: Path):
        with pytest.raises(NSXConfigError):
            project_config._require_app_config(tmp_path)
        with pytest.raises(NSXError):
            project_config._require_app_config(tmp_path)


# ---------------------------------------------------------------------------
# B5: _find_in_dir — pathlib + Windows .exe awareness
# ---------------------------------------------------------------------------


class TestFindInDir:
    """B5: Verify _find_in_dir locates files and tries .exe on Windows."""

    def test_finds_existing_file(self, tmp_path):
        from neuralspotx.operations._doctor import _find_in_dir

        (tmp_path / "clang").write_text("", encoding="utf-8")
        assert _find_in_dir(tmp_path, "clang") == str(tmp_path / "clang")

    def test_returns_none_for_missing(self, tmp_path):
        from neuralspotx.operations._doctor import _find_in_dir

        assert _find_in_dir(tmp_path, "no-such-tool") is None

    @patch("neuralspotx.operations._doctor.sys")
    def test_tries_exe_suffix_on_windows(self, mock_sys, tmp_path):
        from neuralspotx.operations._doctor import _find_in_dir

        mock_sys.platform = "win32"
        # Only the .exe variant exists.
        (tmp_path / "clang.exe").write_text("", encoding="utf-8")
        assert _find_in_dir(tmp_path, "clang") == str(tmp_path / "clang.exe")

    @patch("neuralspotx.operations._doctor.sys")
    def test_prefers_bare_name_over_exe_on_windows(self, mock_sys, tmp_path):
        from neuralspotx.operations._doctor import _find_in_dir

        mock_sys.platform = "win32"
        (tmp_path / "clang").write_text("", encoding="utf-8")
        (tmp_path / "clang.exe").write_text("", encoding="utf-8")
        # Bare name is tried first and returned.
        assert _find_in_dir(tmp_path, "clang") == str(tmp_path / "clang")


# ---------------------------------------------------------------------------
# B6: extract_view_command — ninja subprocess fallback
# ---------------------------------------------------------------------------


class TestExtractViewCommandNinjaSubprocess:
    """B6: ninja -t commands fast-path and graceful fallback."""

    def test_uses_ninja_subprocess_when_available(self, tmp_path):
        """When ninja -t commands succeeds, the file is not parsed."""
        target = "app_view"
        ninja_output = "cd /build && /usr/bin/viewer --port 0\n"

        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=ninja_output)
        with patch("neuralspotx.subprocess_utils.subprocess.run", return_value=completed):
            result = extract_view_command(tmp_path, target)
        assert result == ["/usr/bin/viewer", "--port", "0"]

    def test_falls_back_to_file_when_ninja_fails(self, tmp_path):
        """When ninja is absent, the build.ninja file is parsed normally."""
        target = "app_view"
        ninja = _NO_CD_PREFIX.format(target=target, cmd="/usr/bin/viewer --flag")
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        with patch(
            "neuralspotx.subprocess_utils.subprocess.run",
            side_effect=FileNotFoundError("ninja not found"),
        ):
            result = extract_view_command(tmp_path, target)
        assert result == ["/usr/bin/viewer", "--flag"]

    def test_falls_back_when_ninja_returns_error(self, tmp_path):
        """Non-zero exit from ninja triggers file-parsing fallback."""
        target = "app_view"
        ninja = _NO_CD_PREFIX.format(target=target, cmd="/usr/bin/viewer")
        (tmp_path / "build.ninja").write_text(ninja, encoding="utf-8")

        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="error")
        with patch("neuralspotx.subprocess_utils.subprocess.run", return_value=completed):
            result = extract_view_command(tmp_path, target)
        assert result == ["/usr/bin/viewer"]
