"""App reset resolves CMake board facts without building or touching hardware."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from neuralspotx import NSXConfigError, api, cli
from neuralspotx.operations import _hardware


def _app(tmp_path: Path, board: str = "apollo510b_evb") -> tuple[Path, Path]:
    app = tmp_path / "app with spaces"
    app.mkdir()
    (app / "nsx.yml").write_text(
        f"schema_version: 2\nproject:\n  name: demo\ntargets:\n"
        f"  default: {board}\n  supported: [{board}, apollo510_evb]\n",
        encoding="utf-8",
    )
    build = app / "build" / board
    build.mkdir(parents=True)
    (build / "build.ninja").write_text("# configured\n", encoding="utf-8")
    _cache(app, build, board)
    return app, build


def _cache(app: Path, build: Path, board: str) -> None:
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={app.as_posix()}\nNSX_BOARD:STRING={board}\n"
        "NSX_RESET_DEVICE:INTERNAL=CustomDevice\nNSX_RESET_SPEED_KHZ:INTERNAL=1200\n"
        "NSX_JLINK_SERIAL:STRING=1234\n",
        encoding="utf-8",
    )


@pytest.fixture
def reset_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_script(script: str, **kwargs: object) -> str:
        calls.append({"script": script, **kwargs})
        return ""

    monkeypatch.setattr(_hardware, "_run_jlink_script", fake_script)
    return calls


@pytest.mark.parametrize("board", ["apollo510b_evb", "my_custom_board"])
def test_reset_uses_configured_board_and_probe(
    tmp_path: Path, reset_calls: list[dict[str, object]], board: str
) -> None:
    app, _ = _app(tmp_path, board)
    result = api.reset_target(app_dir=app)
    assert result.device == "CustomDevice"
    assert result.speed_khz == 1200
    assert result.probe_serial == "1234"
    assert reset_calls[0]["script"] == "r\ng\nexit\n"


def test_reset_board_and_build_override(
    tmp_path: Path, reset_calls: list[dict[str, object]]
) -> None:
    app, _ = _app(tmp_path)
    build = tmp_path / "other build"
    build.mkdir()
    (build / "build.ninja").touch()
    _cache(app, build, "apollo510_evb")
    result = api.reset_target(
        app_dir=app,
        board="apollo510_evb",
        build_dir=build,
        speed_khz=2000,
        probe_serial="5678",
        interface="JTAG",
        kind="swpoi",
    )
    assert result.speed_khz == 2000
    assert result.probe_serial == "5678"
    assert result.interface == "JTAG"
    assert "w4 40000004 1b" in str(reset_calls[0]["script"])


def test_standalone_bypasses_app_lookup(
    tmp_path: Path, reset_calls: list[dict[str, object]]
) -> None:
    result = api.reset_target(device="Explicit", app_dir=tmp_path / "absent")
    assert result.device == "Explicit"
    assert result.speed_khz == 4000
    assert result.probe_serial is None
    assert len(reset_calls) == 1


@pytest.mark.parametrize("change", ["missing", "old", "board", "source", "speed", "zero", "device"])
def test_invalid_configuration_never_calls_probe(
    tmp_path: Path, reset_calls: list[dict[str, object]], change: str
) -> None:
    app, build = _app(tmp_path)
    cache = build / "CMakeCache.txt"
    text = cache.read_text(encoding="utf-8")
    if change == "missing":
        (build / "build.ninja").unlink()
    elif change == "old":
        text = text.replace("NSX_RESET_DEVICE:INTERNAL=CustomDevice\n", "")
    elif change == "board":
        text = text.replace("NSX_BOARD:STRING=apollo510b_evb", "NSX_BOARD:STRING=apollo510_evb")
    elif change == "source":
        text = text.replace(app.as_posix(), tmp_path.as_posix())
    elif change == "speed":
        text = text.replace("=1200", "=fast")
    elif change == "zero":
        text = text.replace("=1200", "=0")
    else:
        text = text.replace("=CustomDevice", "=")
    cache.write_text(text, encoding="utf-8")
    with pytest.raises(NSXConfigError, match="nsx configure"):
        api.reset_target(app_dir=app)
    assert not reset_calls


def test_cli_app_and_standalone(tmp_path: Path, reset_calls: list[dict[str, object]]) -> None:
    app, _ = _app(tmp_path)
    assert cli.main(["reset", "--app-dir", str(app)]) == 0
    assert reset_calls[-1]["device"] == "CustomDevice"
    assert cli.main(["reset", str(app), "--speed-khz", "800"]) == 0
    assert reset_calls[-1]["speed_khz"] == 800
    assert cli.main(["reset", "--device", "Explicit", "--app-dir", "absent"]) == 0
    assert reset_calls[-1]["device"] == "Explicit"


def test_real_cmake_exports_and_clears_resolved_settings(
    tmp_path: Path, reset_calls: list[dict[str, object]]
) -> None:
    app, build = _app(tmp_path, "my_custom_board")
    # Configure actual packaged helper code with a host-only target: no SDK,
    # compiler, network, probe, or guessed Ninja command text is needed.
    helper = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake/nsx_helpers.cmake"
    (build / "CMakeCache.txt").unlink()
    cmake = app / "CMakeLists.txt"
    prefix = (
        "cmake_minimum_required(VERSION 3.20)\nproject(demo NONE)\n"
        f'include("{helper.as_posix()}")\nadd_custom_target(demo)\n'
    )
    cmake.write_text(
        prefix + 'set(NSX_SEGGER_DEVICE "BoardOverride")\nset(NSX_SEGGER_IF_SPEED 750)\n'
        "nsx_add_segger_targets(demo)\n",
        encoding="utf-8",
    )
    cmd = ["cmake", "-S", str(app), "-B", str(build), "-G", "Ninja", "-DNSX_BOARD=my_custom_board"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    result = api.reset_target(app_dir=app)
    assert result.device == "BoardOverride"
    assert result.speed_khz == 750
    cmake.write_text(prefix + "nsx_add_segger_targets(demo)\n", encoding="utf-8")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    with pytest.raises(NSXConfigError, match="settings are missing"):
        api.reset_target(app_dir=app)
    assert len(reset_calls) == 1
