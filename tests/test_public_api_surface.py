"""Tests for the PR3 modularity work.

Covers:
* The public ``neuralspotx`` package exports the lock/sync/outdated/update
  request types and dispatcher functions.
* ``api.update_app`` dispatches to ``operations.update_app_impl``.
* The CLI parses ``--timeout`` for the build-style commands and threads
  the value through ``api.*`` (and therefore through ``timeout_budget``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import neuralspotx
import neuralspotx.api as api
import neuralspotx.cli as cli
import neuralspotx.operations as operations


def test_public_surface_exports_lock_sync_outdated_update() -> None:
    expected = {
        "AppLockRequest",
        "AppSyncRequest",
        "AppOutdatedRequest",
        "AppUpdateRequest",
        "lock_app",
        "sync_app",
        "outdated_app",
        "update_app",
    }
    assert expected.issubset(set(neuralspotx.__all__))
    for name in expected:
        assert getattr(neuralspotx, name) is getattr(api, name)


def test_app_update_request_roundtrip() -> None:
    req = neuralspotx.AppUpdateRequest(app_dir="/tmp/app", modules=["nsx-utils"], timeout_s=30.0)
    assert req.app_dir == "/tmp/app"
    assert req.modules == ["nsx-utils"]
    assert req.timeout_s == 30.0


def test_update_app_dispatches_to_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, list[str] | None]] = []

    def fake_update(app_dir: Path, *, modules: list[str] | None = None) -> None:
        calls.append((app_dir, modules))

    monkeypatch.setattr(operations, "update_app_impl", fake_update)

    app_dir = tmp_path / "app"
    neuralspotx.update_app(neuralspotx.AppUpdateRequest(app_dir=app_dir, modules=["a", "b"]))

    assert calls == [(app_dir.resolve(), ["a", "b"])]


def test_clean_app_accepts_timeout_kwarg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen_timeouts: list[float | None] = []

    def fake_clean(app_dir: Path, **_kwargs: object) -> None:
        # Read the active timeout budget via the subprocess_utils contextvar.
        from neuralspotx.subprocess_utils import _TIMEOUT

        seen_timeouts.append(_TIMEOUT.get())

    monkeypatch.setattr(operations, "clean_app_impl", fake_clean)

    app_dir = tmp_path / "app"
    neuralspotx.clean_app(app_dir=app_dir, full=True, timeout_s=12.5)

    assert seen_timeouts == [12.5]


@pytest.mark.parametrize(
    "subcmd",
    ["configure", "build", "flash", "clean", "lock", "sync", "update"],
)
def test_cli_parser_accepts_timeout_flag(subcmd: str) -> None:
    parser = cli._build_parser()
    # Every supported subcommand must accept `--timeout SECONDS`.
    args = parser.parse_args([subcmd, "--app-dir", ".", "--timeout", "7"])
    assert args.timeout == 7.0


def test_cli_build_threads_timeout_through_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_build_app(app_dir: object, **kwargs: object) -> None:
        captured["app_dir"] = app_dir
        captured.update(kwargs)

    monkeypatch.setattr(cli.api, "build_app", fake_build_app)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nsx.yml").write_text("name: x\nboard: apollo510_evb\nmodules: []\n")

    rc = cli.main(["build", "--app-dir", str(tmp_path), "--timeout", "42"])
    assert rc == 0
    assert captured.get("timeout_s") == 42.0


# ---------------------------------------------------------------------------
# R18: CLI/API parity — every cmd_* handler dispatches through api.*
# ---------------------------------------------------------------------------


class TestCliApiParity:
    """Verify that CLI command handlers route through the public API layer."""

    @staticmethod
    def _nsx_yml(tmp_path: Path) -> Path:
        p = tmp_path / "nsx.yml"
        p.write_text("name: x\nboard: apollo510_evb\nmodules: []\n")
        return p

    def test_cmd_create_app_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "create_app", fake)
        target = tmp_path / "new_app"
        cli.cmd_create_app(
            cli.argparse.Namespace(
                app_dir=str(target),
                board="apollo510_evb",
                soc=None,
                force=False,
                no_bootstrap=False,
            )
        )
        assert len(calls) == 1
        assert calls[0]["board"] == "apollo510_evb"

    def test_cmd_doctor_routes_through_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from neuralspotx.models import DoctorReport

        called = []

        def fake_doctor() -> DoctorReport:
            called.append(True)
            return DoctorReport(checks=())

        monkeypatch.setattr(cli.api, "doctor", fake_doctor)
        cli.cmd_doctor(cli.argparse.Namespace())
        assert called

    def test_cmd_configure_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "configure_app", fake)
        cli.cmd_configure(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                board=None,
                build_dir=None,
                toolchain=None,
                timeout=None,
            )
        )
        assert len(calls) == 1

    def test_cmd_view_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "view_app", fake)
        cli.cmd_view(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                board=None,
                build_dir=None,
                toolchain=None,
                no_reset_on_open=False,
                reset_delay_ms=400,
                timeout=None,
            )
        )
        assert len(calls) == 1
        assert calls[0]["reset_on_open"] is True

    def test_cmd_flash_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "flash_app", fake)
        cli.cmd_flash(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                board=None,
                build_dir=None,
                toolchain=None,
                jobs=8,
                timeout=None,
            )
        )
        assert len(calls) == 1

    def test_cmd_clean_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "clean_app", fake)
        cli.cmd_clean(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                board=None,
                build_dir=None,
                toolchain=None,
                full=True,
                timeout=None,
            )
        )
        assert len(calls) == 1
        assert calls[0]["full"] is True

    def test_cmd_lock_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> Path:
            calls.append({"app_dir": app_dir, **kw})
            return tmp_path / "nsx.lock"

        monkeypatch.setattr(cli.api, "lock_app", fake)
        cli.cmd_lock(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                update=True,
                modules=None,
                check=False,
                timeout=None,
            )
        )
        assert len(calls) == 1
        assert calls[0]["update"] is True

    def test_cmd_sync_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "sync_app", fake)
        cli.cmd_sync(
            cli.argparse.Namespace(app_dir=str(tmp_path), frozen=False, force=True, timeout=None)
        )
        assert len(calls) == 1
        assert calls[0]["force"] is True

    def test_cmd_outdated_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        from neuralspotx.models import OutdatedReport

        def fake(app_dir: object, **kw: object) -> OutdatedReport:
            calls.append({"app_dir": app_dir, **kw})
            return OutdatedReport(checked=())

        monkeypatch.setattr(cli.api, "outdated_app", fake)
        cli.cmd_outdated(
            cli.argparse.Namespace(app_dir=str(tmp_path), json=False, exit_code=False, timeout=None)
        )
        assert len(calls) == 1

    def test_cmd_update_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> None:
            calls.append({"app_dir": app_dir, **kw})

        monkeypatch.setattr(cli.api, "update_app", fake)
        cli.cmd_update(
            cli.argparse.Namespace(app_dir=str(tmp_path), modules=["nsx-core"], timeout=None)
        )
        assert len(calls) == 1
        assert calls[0]["modules"] == ["nsx-core"]

    def test_cmd_module_add_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx.models import ModuleChange

        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, module: object, **kw: object) -> list[ModuleChange]:
            calls.append({"app_dir": app_dir, "module": module, **kw})
            return [ModuleChange(name=str(module), before=None, after="main", action="added")]

        monkeypatch.setattr(cli.api, "add_module", fake)
        cli.cmd_module_add(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                module="nsx-uart",
                dry_run=False,
                local=False,
                vendored=False,
            )
        )
        assert len(calls) == 1
        assert calls[0]["module"] == "nsx-uart"

    def test_cmd_module_remove_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx.models import ModuleChange

        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, module: object, **kw: object) -> list[ModuleChange]:
            calls.append({"app_dir": app_dir, "module": module, **kw})
            return [ModuleChange(name=str(module), before="main", after=None, action="removed")]

        monkeypatch.setattr(cli.api, "remove_module", fake)
        cli.cmd_module_remove(
            cli.argparse.Namespace(app_dir=str(tmp_path), module="nsx-uart", dry_run=False)
        )
        assert len(calls) == 1

    def test_cmd_module_update_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx.models import ModuleChange

        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, **kw: object) -> list[ModuleChange]:
            calls.append({"app_dir": app_dir, **kw})
            return [
                ModuleChange(
                    name=str(kw.get("module") or "x"),
                    before="a",
                    after="b",
                    action="updated",
                    dry_run=True,
                )
            ]

        monkeypatch.setattr(cli.api, "update_modules", fake)
        cli.cmd_module_update(
            cli.argparse.Namespace(app_dir=str(tmp_path), module="nsx-uart", dry_run=True)
        )
        assert len(calls) == 1
        assert calls[0]["dry_run"] is True

    def test_cmd_module_register_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx.models import ModuleChange

        self._nsx_yml(tmp_path)
        calls: list[dict[str, object]] = []

        def fake(app_dir: object, module: object, **kw: object) -> ModuleChange:
            calls.append({"app_dir": app_dir, "module": module, **kw})
            return ModuleChange(name=str(module), before=None, after="main", action="added")

        monkeypatch.setattr(cli.api, "register_module", fake)
        cli.cmd_module_register(
            cli.argparse.Namespace(
                app_dir=str(tmp_path),
                module="my-mod",
                metadata="meta.yaml",
                project="my-project",
                project_url=None,
                project_revision=None,
                project_path=None,
                project_local_path=None,
                override=False,
                dry_run=False,
            )
        )
        assert len(calls) == 1
        assert calls[0]["module"] == "my-mod"

    def test_cmd_module_init_routes_through_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from neuralspotx.models import ModuleChange

        calls: list[dict[str, object]] = []

        def fake(module_dir: object, **kw: object) -> ModuleChange:
            calls.append({"module_dir": module_dir, **kw})
            return ModuleChange(
                name=str(kw.get("module_name") or "new-mod"),
                before=None,
                after=str(kw.get("version") or "0.1.0"),
                action="added",
            )

        monkeypatch.setattr(cli.api, "init_module", fake)
        cli.cmd_module_init(
            cli.argparse.Namespace(
                module_dir=str(tmp_path / "new-mod"),
                name="my-mod",
                type="runtime",
                summary="A module",
                version="0.1.0",
                dependency=None,
                board=None,
                soc=None,
                toolchain=None,
                force=False,
            )
        )
        assert len(calls) == 1
        assert calls[0]["module_name"] == "my-mod"


class TestCliApiParityGaps:
    """Document CLI commands that bypass the API layer.

    These tests verify the current behavior (direct internal calls) so
    any future API-routing refactor can detect regressions.
    """

    def test_cmd_module_list_calls_internal_registry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """cmd_module_list bypasses api.list_modules — uses _module_discovery_records directly."""
        from neuralspotx.module_discovery import resolve_module_context

        calls: list[bool] = []
        original = resolve_module_context

        def spy(*a: object, **kw: object) -> object:
            calls.append(True)
            return original(*a, **kw)

        monkeypatch.setattr(cli, "resolve_module_context", spy)
        # --registry-only avoids needing an nsx.yml
        cli.cmd_module_list(cli.argparse.Namespace(app_dir=None, registry_only=True, json=False))
        assert calls, "cmd_module_list should call resolve_module_context (not api.list_modules)"

    def test_cmd_module_validate_calls_internal_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cmd_module_validate bypasses api.validate_module_metadata — calls load_yaml directly."""
        load_calls: list[object] = []
        original_load = cli.load_yaml

        def spy(path: object) -> object:
            load_calls.append(path)
            return original_load(path)

        monkeypatch.setattr(cli, "load_yaml", spy)
        meta = tmp_path / "nsx-module.yaml"
        meta.write_text(
            "schema_version: 1\n"
            "module:\n  name: test-mod\n  type: runtime\n  version: 0.1.0\n"
            "support:\n  ambiqsuite: true\n  zephyr: false\n"
            "build:\n  cmake:\n    package: test_mod\n    targets: [test_mod]\n"
            "depends:\n  required: []\n  optional: []\n"
            "compatibility:\n  boards: ['*']\n  socs: ['*']\n  toolchains: ['*']\n"
        )
        cli.cmd_module_validate(cli.argparse.Namespace(metadata=str(meta), json=False))
        assert load_calls, "cmd_module_validate should call load_yaml directly"
