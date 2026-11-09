"""Console contracts are advisory and must not change transport execution."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import AppRttRequest, Event, NSXConfigError, api, operations
from neuralspotx import _rtt_capture as runtime
from neuralspotx.models import AppConfig, ConsoleConfig, NsxProject, RttResult, RttSettings
from neuralspotx.operations import _build, _rtt


def manifest(**kwargs: Any) -> dict[str, Any]:
    return {"schema_version": 2, "project": {"name": "demo"}, **kwargs}


@pytest.mark.parametrize("value", [None, {"transport": "swo"}, {"transport": "rtt"}])
def test_loader_and_direct_model_agree(value: object) -> None:
    data = manifest(console=value)
    expected = None if value is None else ConsoleConfig.from_value(value)
    assert NsxProject.from_mapping(data).app_config().console_for_board("custom") == expected
    assert AppConfig.from_mapping(data).console_for_board("custom") == expected


@pytest.mark.parametrize(
    "value",
    [
        [],
        "rtt",
        {},
        {"transport": "uart"},
        {"transport": []},
        {"transport": "rtt", "typo": 0},
        {"transport": "swo", "rtt_channel": 0},
    ]
    + [{"transport": "rtt", "rtt_channel": c} for c in [True, False, "0", 0.0, -1, 1, None]],
)
@pytest.mark.parametrize("override", [False, True])
def test_invalid_declarations_rejected_even_for_unselected_board(
    value: object, override: bool
) -> None:
    data = (
        manifest(console=value)
        if not override
        else manifest(targets={"supported": {"unused": {"console": value}}})
    )
    for parse in (NsxProject.from_mapping, AppConfig.from_mapping):
        with pytest.raises(NSXConfigError) as exc:
            parse(data)
        assert exc.value.field and "console" in exc.value.field


def test_inheritance_replacement_null_and_alias() -> None:
    config = AppConfig.from_mapping(
        manifest(
            console={"transport": "rtt", "rtt_channel": 0},
            targets={
                "supported": {
                    "apollo510_evb": {"console": {"transport": "swo"}},
                    "clear": {"console": None},
                    "inherit": {},
                    "null_entry": None,
                }
            },
        )
    )
    assert config.console_for_board("APOLLO510_EVB") == ConsoleConfig("swo")
    assert config.resolve_target("apollo510_evb").console == ConsoleConfig("swo")
    assert config.console_for_board("clear") is None
    for board in ("inherit", "null_entry", "undeclared"):
        assert config.console_for_board(board) == ConsoleConfig("rtt", 0)
    for targets in ({"target": {"board": "custom"}}, {"targets": {"supported": ["custom"]}}):
        config = AppConfig.from_mapping(manifest(console={"transport": "rtt"}, **targets))
        assert config.resolve_target("custom").console == ConsoleConfig("rtt", 0)


@pytest.fixture
def console_app(tmp_path: Path) -> Path:
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest(console={"transport": "swo"})))
    return tmp_path


def test_rtt_emitter_forwarded_once_before_capture(
    console_app: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build = console_app / "build"
    (build / "nsx-artifacts").mkdir(parents=True)
    (build / "nsx-artifacts/demo.path").write_text(str(build / "demo.elf") + "\n")
    events: list[Event] = []
    data: list[bytes] = []
    settings = RttSettings(
        console_app, "custom", build, "demo", build / "demo.elf", 123, "dev", 1000, "123"
    )
    monkeypatch.setattr(_rtt, "app_debug_settings", lambda *a, **kw: settings)
    monkeypatch.setattr(_rtt, "_rtt_address", lambda *_: 123)

    def capture(resolved: RttSettings, **kwargs: Any) -> RttResult:
        assert len(events) == 1
        assert events[0].data["code"] == "console_transport_mismatch"
        kwargs["on_data"](b"raw\xff")
        return RttResult(resolved, 4, None)

    monkeypatch.setattr(operations, "rtt_app_impl", capture)
    monkeypatch.setattr(
        runtime, "_start_child", lambda *a, **kw: pytest.fail("native worker started")
    )
    api.rtt_app(
        AppRttRequest(console_app, board="custom", build_dir=build),
        emit=events.append,
        on_data=data.append,
    )
    assert data == [b"raw\xff"]
    assert capsys.readouterr() == ("", "")
    events.clear()
    (build / "nsx-artifacts/other.path").write_text(str(build / "other.elf") + "\n")
    api.resolve_rtt_app(
        AppRttRequest(console_app, board="custom", build_dir=build, target="other"),
        emit=events.append,
    )
    assert events == []


@pytest.mark.parametrize("transport, expected", [("rtt", 1), ("swo", 0), (None, 0)])
def test_view_warns_before_glue_and_preserves_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str | None, expected: int
) -> None:
    declaration = {"transport": transport} if transport else None
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(manifest(console=declaration)))
    events: list[Event] = []

    class StopAtGlue(Exception):
        pass

    def glue(*args: Any, **kwargs: Any) -> None:
        assert len(events) == expected
        raise StopAtGlue

    monkeypatch.setattr(_build, "warn_if_lock_stale", lambda *a: None)
    monkeypatch.setattr(_build, "regenerate_active_board_glue", glue)
    with pytest.raises(StopAtGlue):
        api.view_app(tmp_path, board="custom", emit=events.append)


def test_invalid_metadata_prevents_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "nsx.yml").write_text(
        yaml.safe_dump(manifest(console={"transport": "rtt", "rtt_channel": True}))
    )
    monkeypatch.setattr(
        _build, "regenerate_active_board_glue", lambda *a, **kw: pytest.fail("glue mutated")
    )
    monkeypatch.setattr(_rtt, "app_debug_settings", lambda *a, **kw: pytest.fail("debug accessed"))
    for operation in (
        lambda: api.view_app(tmp_path, board="custom"),
        lambda: api.rtt_app(AppRttRequest(tmp_path, board="custom")),
    ):
        with pytest.raises(NSXConfigError):
            operation()
