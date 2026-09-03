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
from neuralspotx._errors import NSXConfigError
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
    monkeypatch.setattr(_build_mod, "find_segger_tool", lambda _names: None)
    monkeypatch.setattr(_build_mod, "_run_cmake_configure", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "run", lambda *a, **k: None)
    monkeypatch.setattr(
        _build_mod, "run_capture", lambda *a, **k: type("R", (), {"stdout": "", "stderr": ""})()
    )
    monkeypatch.setattr(_build_mod, "print_captured_output", lambda *a, **k: None)
    monkeypatch.setattr(_build_mod, "flash_programming_verified", lambda _output: True)
    monkeypatch.setattr(
        _build_mod,
        "validate_flash_recipe",
        lambda build_dir, target: (
            build_dir / f"{target}.bin",
            build_dir / "jlink" / target / "flash_cmds.jlink",
        ),
    )


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


class TestSdkRootEscapeHatch:
    """``sdk_root`` is validated before any module sync and refused with frozen."""

    @staticmethod
    def _configured_app(tmp_path: Path) -> Path:
        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        build_dir = tmp_path / "build" / "apollo510_evb"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "build.ninja").write_text("# already configured\n")
        return build_dir

    @pytest.mark.parametrize(
        "operation",
        [configure_app_impl, build_app_impl, flash_app_impl],
        ids=["configure", "build", "flash"],
    )
    def test_missing_sdk_root_dir_is_rejected_before_module_sync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: Any
    ) -> None:
        import neuralspotx.operations._build as _build_mod

        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        sync_calls: list[object] = []
        monkeypatch.setattr(_build_mod, "_ensure_app_modules", lambda *a, **k: sync_calls.append(a))

        with pytest.raises(NSXConfigError, match="--sdk-root is not a directory"):
            operation(tmp_path, sdk_root=tmp_path / "does-not-exist")
        assert sync_calls == []

    def test_view_rejects_missing_sdk_root_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import neuralspotx.operations._build as _build_mod
        from neuralspotx.operations import view_app_impl

        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        sync_calls: list[object] = []
        monkeypatch.setattr(_build_mod, "_ensure_app_modules", lambda *a, **k: sync_calls.append(a))

        with pytest.raises(NSXConfigError, match="--sdk-root is not a directory"):
            view_app_impl(tmp_path, sdk_root=tmp_path / "does-not-exist")
        assert sync_calls == []

    @pytest.mark.parametrize(
        "operation",
        [configure_app_impl, build_app_impl, flash_app_impl],
        ids=["configure", "build", "flash"],
    )
    def test_sdk_root_with_frozen_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: Any
    ) -> None:
        """An out-of-tree SDK is not described by nsx.lock; frozen cannot verify it."""
        import neuralspotx.operations._build as _build_mod

        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        sdk = tmp_path / "sdk"
        sdk.mkdir()
        sync_calls: list[object] = []
        monkeypatch.setattr(_build_mod, "_ensure_app_modules", lambda *a, **k: sync_calls.append(a))

        with pytest.raises(NSXConfigError, match="cannot be combined with --frozen"):
            operation(tmp_path, sdk_root=sdk, frozen=True)
        assert sync_calls == []

    def test_sdk_root_warns_and_is_passed_to_configure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import neuralspotx.operations._build as _build_mod

        _make_vendored(tmp_path, "my-vend")
        _write_nsx_yml(tmp_path, [{"name": "my-vend", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        sdk = tmp_path / "sdk"
        sdk.mkdir()
        warnings: list[str] = []
        configure_calls: list[dict[str, object]] = []
        monkeypatch.setattr(_build_mod, "warn", lambda msg, **_k: warnings.append(msg))
        monkeypatch.setattr(
            _build_mod,
            "_run_cmake_configure",
            lambda *_a, **kwargs: configure_calls.append(kwargs),
        )

        configure_app_impl(tmp_path, sdk_root=sdk)

        assert [call["sdk_root"] for call in configure_calls] == [sdk]
        assert len(warnings) == 1
        assert "out-of-tree AmbiqSuite" in warnings[0]
        assert "nsx.lock" in warnings[0] and "--frozen" in warnings[0]

    def test_plain_build_warns_when_tree_carries_cached_sdk_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cached --sdk-root stays in force on a plain build, but not silently."""
        import neuralspotx.operations._build as _build_mod

        build_dir = self._configured_app(tmp_path)
        sdk = tmp_path / "sdk"
        sdk.mkdir()
        (build_dir / "CMakeCache.txt").write_text(
            f"NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH={sdk}\n", encoding="utf-8"
        )
        warnings: list[str] = []
        configure_calls: list[dict[str, object]] = []
        monkeypatch.setattr(_build_mod, "warn", lambda msg, **_k: warnings.append(msg))
        monkeypatch.setattr(
            _build_mod,
            "_run_cmake_configure",
            lambda *_a, **kwargs: configure_calls.append(kwargs),
        )

        build_app_impl(tmp_path)

        assert configure_calls == []
        assert [w for w in warnings if "still uses it" in w and str(sdk) in w]

        # A tree with no cached override stays quiet.
        (build_dir / "CMakeCache.txt").write_text(
            "NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH=\n", encoding="utf-8"
        )
        warnings.clear()
        build_app_impl(tmp_path)
        assert not [w for w in warnings if "still uses it" in w]

    def test_build_reconfigures_when_sdk_root_differs_from_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit sdk_root that the build tree was not configured with

        must not be silently ignored just because build.ninja exists.
        """
        import neuralspotx.operations._build as _build_mod

        build_dir = self._configured_app(tmp_path)
        (build_dir / "CMakeCache.txt").write_text(
            "NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH=\n", encoding="utf-8"
        )
        sdk = tmp_path / "sdk"
        sdk.mkdir()
        configure_calls: list[dict[str, object]] = []
        monkeypatch.setattr(_build_mod, "warn", lambda *_a, **_k: None)
        monkeypatch.setattr(
            _build_mod,
            "_run_cmake_configure",
            lambda *_a, **kwargs: configure_calls.append(kwargs),
        )

        build_app_impl(tmp_path, sdk_root=sdk)
        assert [call["sdk_root"] for call in configure_calls] == [sdk]

        # Same override already cached -> no reconfigure.
        (build_dir / "CMakeCache.txt").write_text(
            f"NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH={sdk}\n", encoding="utf-8"
        )
        configure_calls.clear()
        build_app_impl(tmp_path, sdk_root=sdk)
        assert configure_calls == []

        # No sdk_root keeps whatever the tree was configured with.
        build_app_impl(tmp_path)
        assert configure_calls == []

    @staticmethod
    def _cache_sdk_override(build_dir: Path, sdk_root: Path) -> str:
        """Cache an override exactly as ``_run_cmake_configure`` writes it.

        Mirrors that function's ``sdk_override`` line via stdlib rather than
        via ``_sdk_root_cache_matches``, so the assertions below compare the
        read side against an independently derived write side.
        """

        cached = str(Path(sdk_root).expanduser().resolve())
        (build_dir / "CMakeCache.txt").write_text(
            f"NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH={cached}\n", encoding="utf-8"
        )
        return cached

    def test_cache_match_accepts_absolute_and_relative_sdk_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A relative spelling of the cached override must still match.

        ``_run_cmake_configure`` writes the override as
        ``Path(sdk_root).expanduser().resolve()``; comparing an API caller's
        raw spelling against that would reconfigure on every build/flash/view
        even though the override is unchanged.
        """
        from neuralspotx.operations._build import _sdk_root_cache_matches

        sdk = tmp_path / "AmbiqSuite"
        sdk.mkdir()
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        cached = self._cache_sdk_override(build_dir, sdk)
        # Anchor the relative spelling to the cached value's own directory:
        # on Windows the session CWD can sit on a different drive from
        # tmp_path, and no relative path spans two drives.
        monkeypatch.chdir(tmp_path)

        assert _sdk_root_cache_matches(build_dir, Path(cached))
        assert _sdk_root_cache_matches(build_dir, Path("AmbiqSuite"))
        assert not _sdk_root_cache_matches(build_dir, tmp_path / "other-sdk")

    def test_cache_match_accepts_tilde_sdk_root(self, tmp_path: Path) -> None:
        """A ``~``-prefixed spelling of the cached override must still match.

        The home directory is deliberately not monkeypatched.
        ``ntpath.expanduser`` resolves ``~`` from ``USERPROFILE`` (falling back
        to ``HOMEDRIVE`` + ``HOMEPATH``) and never reads ``HOME``, so patching
        ``HOME`` is a silent no-op on Windows. Deriving the cached value from
        the real ``expanduser()`` result keeps this honest on every platform;
        the directory need not exist because ``_sdk_root_cache_matches``
        compares strings and never stats ``sdk_root``.
        """
        from neuralspotx.operations._build import _sdk_root_cache_matches

        spelling = Path("~") / "AmbiqSuite"
        if str(spelling.expanduser()).startswith("~"):
            pytest.skip("no home directory available to expand ~")
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        self._cache_sdk_override(build_dir, spelling)

        assert _sdk_root_cache_matches(build_dir, spelling)
        assert not _sdk_root_cache_matches(build_dir, tmp_path / "other-sdk")


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
        assert f.target is None
        assert f.frozen is False

        with pytest.raises(TypeError):
            AppFlashRequest("app", None, None, None, None, 2, "secondary")  # ty: ignore[too-many-positional-arguments]  # deliberately invalid call; asserts the runtime TypeError

        with pytest.raises(TypeError):
            AppFlashRequest("app", None, None, None, None, 2, True)  # ty: ignore[too-many-positional-arguments]  # deliberately invalid call; no 7th positional
