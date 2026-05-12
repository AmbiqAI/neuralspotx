"""Phase 7 (Issue #68) — CLI UX polish coverage for PR A.

Covers:
- D1: ``api.list_modules`` defaults to lightweight records (no metadata).
- G1: ``nsx --help`` groups commands into Quickstart / Modules /
  Maintenance / Introspection sections.
- G2: ``nsx add`` and ``nsx list-modules`` are top-level aliases routed
  to the same handlers as their ``module`` subcommand counterparts.
- G3: bare ``nsx`` invocation in a project-less context prints a 5-line
  tutorial and exits 0.
- G4: ``nsx doctor`` (success path) prints a ``Next:`` recovery hint.
- G5: ``nsx update`` peeks via ``api.outdated_app``, prints a one-line
  diff summary, and refuses large updates without ``--yes`` when stdin
  is not a tty.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from neuralspotx import api, cli
from neuralspotx._errors import NSXError, NSXToolchainError
from neuralspotx.models import OutdatedModule, OutdatedReport


def _invoke(*args: str) -> tuple[str, str, int]:
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            cli.main(list(args))
        except SystemExit as exc:
            code = int(exc.code) if exc.code is not None else 0
        except NSXToolchainError as exc:
            err.write(str(exc))
            code = 1
    return out.getvalue(), err.getvalue(), code


# ---------------------------------------------------------------------------
# D1
# ---------------------------------------------------------------------------


def test_d1_list_modules_default_is_lightweight() -> None:
    records = api.list_modules(registry_only=True)
    assert records, "registry should not be empty"
    # Lightweight path: parsed nsx-module.yaml is not loaded.
    assert all(not r.metadata_available and r.module is None for r in records)


def test_d1_list_modules_include_metadata_loads_yaml() -> None:
    records = api.list_modules(registry_only=True, include_metadata=True)
    assert any(r.metadata_available and r.module is not None for r in records)


# ---------------------------------------------------------------------------
# G1
# ---------------------------------------------------------------------------


def test_g1_help_is_grouped() -> None:
    stdout, _stderr, code = _invoke("--help")
    assert code == 0
    for header in ("Quickstart:", "Modules:", "Maintenance:", "Introspection:"):
        assert header in stdout, f"expected {header!r} in --help output"


# ---------------------------------------------------------------------------
# G2
# ---------------------------------------------------------------------------


def test_g2_add_alias_routes_to_module_add(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, object]] = []

    def fake_add(app_dir: object, module: object, **kw: object) -> list[object]:
        seen.append({"app_dir": app_dir, "module": module, **kw})
        return []

    monkeypatch.setattr(cli.api, "add_module", fake_add)
    (tmp_path / "nsx.yml").write_text("modules: {}\n")
    code = cli.main(["add", "--app-dir", str(tmp_path), "--dry-run", "nsx-uart"])
    assert code == 0
    assert len(seen) == 1
    assert seen[0]["module"] == "nsx-uart"
    assert seen[0].get("dry_run") is True


def test_g2_list_modules_alias_routes_to_module_list() -> None:
    canonical_out, _, c1 = _invoke("module", "list", "--registry-only", "--json")
    alias_out, _, c2 = _invoke("list-modules", "--registry-only", "--json")
    assert c1 == 0 and c2 == 0
    assert canonical_out == alias_out


# ---------------------------------------------------------------------------
# G3
# ---------------------------------------------------------------------------


def test_g3_bare_invocation_prints_tutorial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    out, _err, code = _invoke()
    assert code == 0
    assert "nsx doctor" in out
    assert "nsx create-app" in out


def test_g3_skipped_when_argv_is_none_but_sys_argv_has_subcommand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Entry-point calls main(argv=None); sys.argv has args → no tutorial."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr("sys.argv", ["nsx", "--help"])
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            cli.main(argv=None)
        except SystemExit:
            pass
    assert "1) nsx doctor" not in out.getvalue()


def test_g3_skipped_when_nsx_yml_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "nsx.yml").write_text("modules: {}\n")
    # Bare nsx with a project should fall through to argparse and error
    # out (no subcommand chosen) rather than print the tutorial.
    out, err, code = _invoke()
    combined = out + err
    assert "1) nsx doctor" not in combined


# ---------------------------------------------------------------------------
# G4
# ---------------------------------------------------------------------------


def test_g4_doctor_success_prints_next_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    from neuralspotx.models import DoctorCheck, DoctorReport

    fake_report = DoctorReport(
        checks=(DoctorCheck(label="cmake", ok=True, required=True, detail="ok", hint=None),),
        notes=(),
    )
    monkeypatch.setattr(cli.api, "doctor", lambda: fake_report)
    out, _err, code = _invoke("doctor")
    assert code == 0
    assert "Next: nsx create-app" in out


# ---------------------------------------------------------------------------
# G5
# ---------------------------------------------------------------------------


def _make_outdated(n: int) -> OutdatedReport:
    mods = tuple(
        OutdatedModule(
            name=f"mod-{i}",
            constraint="main",
            locked=f"old{i:040d}"[:40],
            upstream=f"new{i:040d}"[:40],
            status="outdated",
            url="git@example.com:foo.git",
        )
        for i in range(n)
    )
    return OutdatedReport(checked=mods)


def _write_app(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text("modules: {}\n")


def test_g5_update_prints_one_line_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path)
    monkeypatch.setattr(cli.api, "outdated_app", lambda app_dir, **kw: _make_outdated(1))
    monkeypatch.setattr(cli.api, "update_app", lambda app_dir, **kw: None)
    out, _err, code = _invoke("update", "--app-dir", str(tmp_path))
    assert code == 0
    assert "1 module(s) will move:" in out
    assert "mod-0" in out


def test_g5_update_blocks_large_change_without_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_app(tmp_path)
    monkeypatch.setattr(cli.api, "outdated_app", lambda app_dir, **kw: _make_outdated(5))
    monkeypatch.setattr(cli.api, "update_app", lambda app_dir, **kw: None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), pytest.raises(NSXError):
        cli.cmd_update(
            cli.argparse.Namespace(app_dir=str(tmp_path), modules=[], timeout=None, yes=False)
        )
    assert "5 module(s) will move:" in out.getvalue()


def test_g5_update_proceeds_with_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path)
    update_calls: list[object] = []
    monkeypatch.setattr(cli.api, "outdated_app", lambda app_dir, **kw: _make_outdated(5))
    monkeypatch.setattr(cli.api, "update_app", lambda app_dir, **kw: update_calls.append(app_dir))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = cli.main(["update", "--app-dir", str(tmp_path), "--yes"])
    assert code == 0
    assert len(update_calls) == 1
