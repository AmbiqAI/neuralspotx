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
