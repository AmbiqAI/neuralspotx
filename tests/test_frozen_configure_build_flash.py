"""Tests for the ``frozen`` parameter on configure_app_impl/build_app_impl/
flash_app_impl.

Verifies that ``frozen=True`` protects a hand-patched vendored module from
being silently overwritten by the implicit module-sync that these three
operations perform when a (re)configure is triggered, and that the existing
"skip module-sync entirely when already configured" guards on
build_app_impl/flash_app_impl are unaffected by the new parameter.

All CMake/toolchain side effects are monkeypatched out — these tests only
exercise the module-sync/frozen threading logic, not real builds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXError
from neuralspotx.operations import (
    build_app_impl,
    configure_app_impl,
    flash_app_impl,
    lock_app_impl,
)


def _write_nsx_yml(app_dir: Path, modules: list[dict[str, Any]]) -> None:
    cfg: dict[str, Any] = {
        "schema_version": 2,
        "project": {"name": "testapp"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "baseline": "none",
        "modules": modules,
    }
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _make_vendored(app_dir: Path, name: str, content: str = "hi") -> None:
    mod = app_dir / "modules" / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "hello.txt").write_text(content, encoding="utf-8")


@pytest.fixture(autouse=True)
def _stub_cmake_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub every real subprocess/CMake side effect these operations trigger.

    Keeps these tests focused purely on the module-sync/frozen threading
    logic; none of them need a real toolchain or CMake project.
    """
    import neuralspotx.operations._build as _build_mod

    monkeypatch.setattr(_build_mod, "warn_if_lock_stale", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "regenerate_active_board_glue", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "_run_cmake_configure", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "run", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "run_capture", lambda *a, **k: type("R", (), {"stdout": "", "stderr": ""})())
    monkeypatch.setattr(_build_mod, "print_captured_output", lambda *a, **k: None)


class TestConfigureFrozen:
    def test_frozen_raises_on_drifted_vendored_module(self, tmp_path: Path) -> None:
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)

        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        with pytest.raises(NSXError):
            configure_app_impl(tmp_path, frozen=True)

    def test_non_frozen_silently_repairs_drifted_vendored_module(self, tmp_path: Path) -> None:
        """Regression guard: default (frozen=False) behavior is unchanged."""
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)

        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        # Vendored modules are verify-only regardless of frozen (sync cannot
        # "repair" a vendored/in-tree module — see _sync_vendored_entry), so
        # this only logs a warning; it must not raise.
        configure_app_impl(tmp_path, frozen=False)


class TestBuildFrozen:
    def test_frozen_raises_on_drift_when_no_build_ninja_yet(self, tmp_path: Path) -> None:
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        with pytest.raises(NSXError):
            build_app_impl(tmp_path, frozen=True)

    def test_frozen_skips_module_sync_entirely_when_already_configured(
        self, tmp_path: Path
    ) -> None:
        """Existing behavior preserved: build.ninja present means no module

        sync at all, frozen or not -- drift (even severe drift) is never
        even inspected on this path.
        """
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        build_dir = tmp_path / "build" / "apollo510_evb"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "build.ninja").write_text("# already configured\n")

        build_app_impl(tmp_path, frozen=True)  # must not raise


class TestFlashFrozen:
    def test_frozen_raises_on_drift_when_probe_serial_given(self, tmp_path: Path) -> None:
        """probe_serial always forces a (re)configure (see flash_app_impl's

        docstring) -- frozen changes how the accompanying module sync
        behaves, but does not skip it.
        """
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        build_dir = tmp_path / "build" / "apollo510_evb"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "build.ninja").write_text("# already configured\n")

        with pytest.raises(NSXError):
            flash_app_impl(tmp_path, probe_serial="1160002204", frozen=True)

    def test_frozen_skips_module_sync_when_no_probe_serial_and_already_configured(
        self, tmp_path: Path
    ) -> None:
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        build_dir = tmp_path / "build" / "apollo510_evb"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "build.ninja").write_text("# already configured\n")

        flash_app_impl(tmp_path, frozen=True)  # no probe_serial -> must not raise


class TestViewFrozen:
    def test_frozen_raises_on_drift_when_probe_serial_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """view_app_impl shares flash_app_impl's probe_serial-forces-

        reconfigure trigger, so it must honor frozen identically --
        otherwise AppViewRequest.frozen (inherited from AppActionRequest)
        would be silently accepted but ignored.
        """
        from neuralspotx.operations import view_app_impl

        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "my-vend" / "hello.txt").write_text("MUTATED", encoding="utf-8")

        build_dir = tmp_path / "build" / "apollo510_evb"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "build.ninja").write_text("# already configured\n")

        with pytest.raises(NSXError):
            view_app_impl(tmp_path, probe_serial="1160002204", frozen=True)


class TestRequestPositionalCompat:
    def test_frozen_is_keyword_only_on_request_dataclasses(self) -> None:
        """frozen must not consume a positional slot on AppActionRequest.

        AppActionRequest is a base class: inserting a new positional field
        would silently shift the meaning of positional construction of
        every subclass (e.g. ``AppBuildRequest(app_dir, None, None, None,
        None, "all", 4)`` would bind frozen="all", target=4 with no error).
        Same guard timeout_s already relies on.
        """
        from neuralspotx import AppBuildRequest, AppFlashRequest

        r = AppBuildRequest("app", None, None, None, None, "mytarget", 4)
        assert r.target == "mytarget"
        assert r.jobs == 4
        assert r.frozen is False

        # AppFlashRequest's own 6th positional field is jobs (pre-PR layout
        # preserved): frozen must not have claimed that slot.
        f = AppFlashRequest("app", None, None, None, None, 2)
        assert f.jobs == 2
        assert f.frozen is False

        with pytest.raises(TypeError):
            AppFlashRequest("app", None, None, None, None, 2, True)  # no 7th positional
