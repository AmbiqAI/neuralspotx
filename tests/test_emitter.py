"""Phase 4: structured event emitter."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from neuralspotx import Emitter, Event, default_emitter
from neuralspotx._io import emit, info, line, step, using_emitter, warn


def test_event_to_dict_round_trip() -> None:
    ev = Event(kind="info", message="hello", data={"a": 1})
    d = ev.to_dict()
    assert d == {"kind": "info", "message": "hello", "data": {"a": 1}}


def test_default_emitter_routes_line_to_stdout_and_others_to_stderr() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        default_emitter(Event("line", "L"))
        default_emitter(Event("info", "I"))
        default_emitter(Event("warn", "W"))
        default_emitter(Event("error", "E"))
        default_emitter(Event("step", "S"))
    assert out.getvalue().splitlines() == ["L"]
    assert err.getvalue().splitlines() == ["I", "W", "E", "S"]


def test_using_emitter_captures_all_kinds() -> None:
    captured: list[Event] = []

    def cap(ev: Event) -> None:
        captured.append(ev)

    with using_emitter(cap):
        info("hi", a=1)
        warn("careful")
        step("doing thing")
        line("raw")
        emit(Event("error", "boom", {"code": 7}))

    kinds = [e.kind for e in captured]
    assert kinds == ["info", "warn", "step", "line", "error"]
    assert captured[0].data == {"a": 1}
    assert captured[-1].data == {"code": 7}


def test_using_emitter_none_restores_default() -> None:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), using_emitter(None):
        info("default-routed")
    assert err.getvalue().strip() == "default-routed"
    assert out.getvalue() == ""


def test_emitter_type_alias_exposes_callable() -> None:
    # Smoke test that the Emitter alias is usable for typing.
    cap: list[Event] = []
    fn: Emitter = cap.append
    with using_emitter(fn):
        info("typed")
    assert cap and cap[0].message == "typed"


def test_lock_app_emits_via_active_emitter(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke: the api.lock_app entry point installs the supplied emitter."""
    from neuralspotx import api

    captured: list[Event] = []

    # Patch the operations.lock_app_impl to just emit and return a sentinel.
    def fake_lock(app_dir, *, update=False, modules=None, check=False, quiet=False):  # type: ignore[no-untyped-def]
        from neuralspotx._io import info as _info

        _info("locking", app=str(app_dir))
        return "SENTINEL"

    monkeypatch.setattr(api.operations, "lock_app_impl", fake_lock)

    result = api.lock_app(tmp_path, emit=captured.append)
    assert result == "SENTINEL"
    assert [e.kind for e in captured] == ["info"]
    assert captured[0].message == "locking"
    assert captured[0].data["app"] == str(tmp_path)
