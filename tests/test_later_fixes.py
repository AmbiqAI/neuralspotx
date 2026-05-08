"""Tests for the 'Later' tier of REVIEW.md remediations.

Covers:

* New string-mixed enums: ``Toolchain``, ``Scope``, ``ModuleType``,
  ``OutdatedStatus``, ``ProfileStatus``.  Each must compare equal to its
  legacy string spelling so existing call sites keep working.
* Structured exception hierarchy: ``NSXError`` and its new subclasses,
  including ``NSXTimeoutError`` mapping from ``subprocess.TimeoutExpired``
  via the API ``_invoke`` adapter.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from neuralspotx import (
    NSXConfigError,
    NSXError,
    NSXLockError,
    NSXModuleError,
    NSXResolutionError,
    NSXTimeoutError,
    NSXToolchainError,
    api,
)
from neuralspotx.constants import SUPPORTED_TOOLCHAINS, TOOLCHAIN_VALUES, Toolchain
from neuralspotx.metadata import SUPPORTED_MODULE_TYPES, ModuleType
from neuralspotx.module_discovery import Scope
from neuralspotx.operations import OutdatedStatus, ProfileStatus

# ---------------------------------------------------------------------------
# Enum: Toolchain
# ---------------------------------------------------------------------------


class TestToolchainEnum:
    def test_string_equality_with_legacy_spelling(self):
        assert Toolchain.GCC == "arm-none-eabi-gcc"
        assert Toolchain.ARMCLANG == "armclang"
        assert Toolchain.ATFE == "atfe"

    def test_str_returns_value(self):
        assert str(Toolchain.GCC) == "arm-none-eabi-gcc"

    def test_parse_aliases(self):
        assert Toolchain.parse("gcc") is Toolchain.GCC
        assert Toolchain.parse("arm-none-eabi-gcc") is Toolchain.GCC
        assert Toolchain.parse("ARMCLANG") is Toolchain.ARMCLANG
        assert Toolchain.parse(" atfe ") is Toolchain.ATFE

    def test_parse_unknown_raises(self):
        with pytest.raises(ValueError):
            Toolchain.parse("not-a-toolchain")

    def test_values_set_matches_supported(self):
        # SUPPORTED_TOOLCHAINS keys include both 'gcc' alias and the canonical
        # spelling; TOOLCHAIN_VALUES contains only canonical values.
        assert TOOLCHAIN_VALUES == {"arm-none-eabi-gcc", "armclang", "atfe"}
        assert TOOLCHAIN_VALUES.issubset(set(SUPPORTED_TOOLCHAINS))


# ---------------------------------------------------------------------------
# Enum: Scope
# ---------------------------------------------------------------------------


class TestScopeEnum:
    def test_string_equality(self):
        assert Scope.PACKAGED == "packaged"
        assert Scope.APP_EFFECTIVE == "app-effective"

    def test_str_returns_value(self):
        assert str(Scope.PACKAGED) == "packaged"
        assert str(Scope.APP_EFFECTIVE) == "app-effective"

    def test_resolve_module_context_returns_scope_enum(self, monkeypatch):
        from neuralspotx import module_discovery

        monkeypatch.setattr(module_discovery, "_load_registry", lambda: {})
        _, _, _, scope = module_discovery.resolve_module_context(app_dir=None)
        # Returned value is the enum but compares equal to the legacy string.
        assert scope == "packaged"
        assert isinstance(scope, Scope)


# ---------------------------------------------------------------------------
# Enum: ModuleType
# ---------------------------------------------------------------------------


class TestModuleTypeEnum:
    def test_string_equality(self):
        assert ModuleType.RUNTIME == "runtime"
        assert ModuleType.BOARD == "board"

    def test_supported_set_matches_enum(self):
        assert SUPPORTED_MODULE_TYPES == frozenset(t.value for t in ModuleType)


# ---------------------------------------------------------------------------
# Enum: OutdatedStatus / ProfileStatus
# ---------------------------------------------------------------------------


class TestOutdatedStatusEnum:
    def test_string_equality(self):
        assert OutdatedStatus.UP_TO_DATE == "up-to-date"
        assert OutdatedStatus.OUTDATED == "outdated"

    def test_json_serialises_as_value(self):
        # Mixing str + Enum makes json.dumps emit the underlying string.
        payload = {"status": OutdatedStatus.OUTDATED}
        assert json.loads(json.dumps(payload))["status"] == "outdated"


class TestProfileStatusEnum:
    def test_string_equality(self):
        assert ProfileStatus.ACTIVE == "active"
        assert ProfileStatus.SCAFFOLD == "scaffold"


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_subclasses_inherit_from_base(self):
        for cls in (
            NSXTimeoutError,
            NSXConfigError,
            NSXResolutionError,
            NSXLockError,
            NSXModuleError,
            NSXToolchainError,
        ):
            assert issubclass(cls, NSXError)

    def test_caught_via_base_class(self):
        try:
            raise NSXTimeoutError("boom")
        except NSXError as exc:
            assert "boom" in str(exc)
        else:  # pragma: no cover
            pytest.fail("expected NSXError catch")

    def test_timeout_carries_metadata(self):
        exc = NSXTimeoutError("oops", command="git fetch", timeout_s=12.5)
        assert exc.command == "git fetch"
        assert exc.timeout_s == 12.5


class TestInvokeMapsTimeout:
    def test_timeout_expired_becomes_nsx_timeout_error(self):
        def boom():
            raise subprocess.TimeoutExpired(cmd=["git", "fetch", "x"], timeout=7)

        with pytest.raises(NSXTimeoutError) as ei:
            api._invoke(boom)
        assert ei.value.timeout_s == 7.0
        assert "git fetch x" in (ei.value.command or "")

    def test_invoke_with_return_also_maps_timeout(self):
        def boom():
            raise subprocess.TimeoutExpired(cmd="git ls-remote", timeout=3)

        with pytest.raises(NSXTimeoutError):
            api._invoke_with_return(boom)


class TestInvokeClassifiesSystemExit:
    def test_lock_message_classified(self):
        def boom():
            raise SystemExit("App lock unavailable: another nsx is running")

        with pytest.raises(NSXLockError):
            api._invoke(boom)

    def test_module_message_classified(self):
        def boom():
            raise SystemExit("Unknown module 'foo'")

        with pytest.raises(NSXModuleError):
            api._invoke(boom)

    def test_toolchain_message_classified(self):
        def boom():
            raise SystemExit("Unknown toolchain 'rustc'")

        with pytest.raises(NSXToolchainError):
            api._invoke(boom)

    def test_resolution_message_classified(self):
        def boom():
            raise SystemExit("Failed to resolve ref 'main'")

        with pytest.raises(NSXResolutionError):
            api._invoke(boom)

    def test_config_message_classified(self):
        def boom():
            raise SystemExit("nsx.yml: missing required key 'profile'")

        with pytest.raises(NSXConfigError):
            api._invoke(boom)

    def test_unclassified_falls_back_to_base(self):
        def boom():
            raise SystemExit("something opaque happened")

        with pytest.raises(NSXError) as ei:
            api._invoke(boom)
        # Falls back to the base class — not any of the subclasses.
        assert type(ei.value) is NSXError

    def test_zero_exit_is_silent(self):
        def ok():
            raise SystemExit(0)

        # Should not raise.
        api._invoke(ok)
