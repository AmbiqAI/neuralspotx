"""Regression tests for the "Now" remediation items in REVIEW.md.

These tests pin behaviour for fixes shipped together so future
refactors can't silently regress them:

1. ``_read_yaml`` rejects non-mapping YAML roots with an actionable
   error instead of crashing later with ``AttributeError``.
2. ``_update_nsx_cfg_modules`` preserves vendored entries (parallel to
   the existing local-entry preservation) under remove/update rewrites.
3. The ``api.lock_app`` per-call resolve TTL override does not mutate
   ``os.environ`` and is concurrency-safe (uses ``ContextVar``).
4. ``app_lock`` is fail-closed by default when the lock primitive
   raises an unexpected error and only fails open when
   ``NSX_LOCK_FAIL_OPEN=1`` is set.
5. ``doctor`` reports the J-Link runtime as failing — not OK — when
   the probe exits non-zero without a recognised hint pattern.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from neuralspotx import (
    NSXConfigError,
    _resolve_cache,
    file_lock,
    module_registry,
    project_config,
)

# ---------------------------------------------------------------------------
# 1. YAML root validation
# ---------------------------------------------------------------------------


class TestReadYamlRoot:
    def test_empty_file_is_clear_error(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="empty"):
            project_config._read_yaml(path)

    def test_list_root_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="mapping"):
            project_config._read_yaml(path)

    def test_scalar_root_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("just-a-string\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="mapping"):
            project_config._read_yaml(path)

    def test_invalid_yaml_is_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("foo: : :\n", encoding="utf-8")
        with pytest.raises(NSXConfigError, match="invalid YAML"):
            project_config._read_yaml(path)

    def test_mapping_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "nsx.yml"
        path.write_text("schema_version: 1\nname: app\n", encoding="utf-8")
        cfg = project_config._read_yaml(path)
        assert cfg == {"schema_version": 1, "name": "app"}


# ---------------------------------------------------------------------------
# 2. Vendored module preservation in config rewrite
# ---------------------------------------------------------------------------


class TestVendoredModulePreservation:
    def test_vendored_entry_survives_rewrite(self) -> None:
        cfg = {
            "modules": [
                {"name": "custom-aot", "source": {"vendored": True}},
                {"name": "nsx-uart", "project": "old-proj", "revision": "old"},
            ],
        }
        registry = {
            "modules": {
                "nsx-uart": {
                    "project": "nsx-uart",
                    "revision": "main",
                    "metadata": "modules/nsx-uart/nsx-module.yaml",
                }
            },
            "projects": {
                "nsx-uart": {
                    "url": "https://example.com/nsx-uart.git",
                    "revision": "main",
                    "path": "modules/nsx-uart",
                }
            },
        }
        module_registry._update_nsx_cfg_modules(
            cfg,
            ["custom-aot", "nsx-uart"],
            registry,
        )
        names = [m["name"] for m in cfg["modules"]]
        assert names == ["custom-aot", "nsx-uart"]
        custom = next(m for m in cfg["modules"] if m["name"] == "custom-aot")
        # Critical: vendored marker must round-trip.
        assert custom["source"] == {"vendored": True}

    def test_local_entry_still_preserved(self) -> None:
        cfg = {
            "modules": [
                {"name": "ns-foo", "local": True},
            ],
        }
        registry = {"modules": {}, "projects": {}}
        module_registry._update_nsx_cfg_modules(cfg, ["ns-foo"], registry)
        entry = cfg["modules"][0]
        assert entry["name"] == "ns-foo"
        assert entry["local"] is True


# ---------------------------------------------------------------------------
# 3. Resolve-TTL contextvar override
# ---------------------------------------------------------------------------


class TestResolveTtlOverride:
    def test_override_does_not_mutate_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSX_RESOLVE_TTL", raising=False)
        with _resolve_cache.ttl_override(1234.0):
            assert _resolve_cache._ttl_seconds() == 1234.0
            assert "NSX_RESOLVE_TTL" not in os.environ
        assert _resolve_cache._ttl_seconds() == _resolve_cache._DEFAULT_TTL

    def test_override_takes_precedence_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_RESOLVE_TTL", "10")
        assert _resolve_cache._ttl_seconds() == 10.0
        with _resolve_cache.ttl_override(99.0):
            assert _resolve_cache._ttl_seconds() == 99.0
        # Env value restored after override.
        assert _resolve_cache._ttl_seconds() == 10.0

    def test_override_is_thread_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSX_RESOLVE_TTL", raising=False)
        seen: dict[str, float] = {}
        barrier = threading.Barrier(2)

        def worker_a() -> None:
            with _resolve_cache.ttl_override(11.0):
                barrier.wait()
                # Other thread is in its own override; must not leak.
                seen["a"] = _resolve_cache._ttl_seconds()

        def worker_b() -> None:
            with _resolve_cache.ttl_override(22.0):
                barrier.wait()
                seen["b"] = _resolve_cache._ttl_seconds()

        ta = threading.Thread(target=worker_a)
        tb = threading.Thread(target=worker_b)
        ta.start()
        tb.start()
        ta.join()
        tb.join()
        assert seen == {"a": 11.0, "b": 22.0}


# ---------------------------------------------------------------------------
# 4. app_lock fail-closed default
# ---------------------------------------------------------------------------


class TestAppLockFailClosed:
    def test_unexpected_lock_failure_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NSX_LOCK_FAIL_OPEN", raising=False)

        def boom(_fd: int, *, blocking: bool) -> None:
            raise RuntimeError("simulated primitive failure")

        monkeypatch.setattr(file_lock, "_platform_lock", boom)
        with pytest.raises(file_lock.AppLockUnavailableError, match="simulated"):
            with file_lock.app_lock(tmp_path):
                pass

    def test_fail_open_env_opt_out_proceeds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("NSX_LOCK_FAIL_OPEN", "1")

        def boom(_fd: int, *, blocking: bool) -> None:
            raise RuntimeError("simulated primitive failure")

        monkeypatch.setattr(file_lock, "_platform_lock", boom)
        # Reset warn-once memo so we can observe the warning each test run.
        file_lock._warned.clear()
        ran = False
        with file_lock.app_lock(tmp_path):
            ran = True
        assert ran
        captured = capsys.readouterr()
        assert "file lock unavailable" in captured.err


# ---------------------------------------------------------------------------
# 5. Doctor J-Link runtime: fail on unclassified non-zero exit
# ---------------------------------------------------------------------------


class TestDoctorJLinkRuntime:
    def test_unclassified_called_process_error_is_failure(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import subprocess

        from neuralspotx import operations

        # Force jlink path to be discovered, swo viewer to be discovered,
        # and the subprocess probe to fail with an unrecognised message.
        monkeypatch.setattr(operations._doctor, "find_segger_tool", lambda _names: "/fake/JLinkExe")

        def fake_run(*_args: object, **_kwargs: object) -> object:
            raise subprocess.CalledProcessError(
                returncode=42,
                cmd=["JLinkExe"],
                output="some unknown failure mode\n",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

        # doctor_impl now returns a DoctorReport (no raise) — the
        # CLI handler is responsible for converting !ok into NSXError.
        report = operations.doctor_impl()
        assert report.ok is False
        out = capsys.readouterr().out
        # The J-Link runtime check should appear and be marked FAIL,
        # not OK.
        runtime_lines = [line for line in out.splitlines() if "J-Link runtime" in line]
        assert runtime_lines, "J-Link runtime check missing from doctor output"
        assert not any("OK" in line and "JLinkExe launched" in line for line in runtime_lines), (
            f"runtime falsely reported OK: {runtime_lines}"
        )
