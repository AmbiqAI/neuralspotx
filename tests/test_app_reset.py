"""App reset resolves CMake board facts without building or touching hardware."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from debug_fixtures import make_debug_app

from neuralspotx import NSXConfigError, api, cli, tooling
from neuralspotx.operations import _hardware
from neuralspotx.tooling import JLinkProbe, _JLinkInventoryEntry


def _app(tmp_path: Path, board: str = "apollo510b_evb") -> tuple[Path, Path]:
    return make_debug_app(tmp_path / "app with spaces", board)


def _cache(app: Path, build: Path, board: str) -> None:
    make_debug_app(app, board, build)


@pytest.fixture
def reset_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    monkeypatch.setattr(
        tooling,
        "_list_jlink_inventory",
        lambda: [_JLinkInventoryEntry(JLinkProbe(0, "1234", "fake"), "USB")],
    )
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
    assert result.probe_serial == "1234"
    assert len(reset_calls) == 1


@pytest.mark.parametrize("change", ["missing", "old", "board", "source", "speed", "zero", "device"])
def test_invalid_configuration_never_calls_probe(
    tmp_path: Path, reset_calls: list[dict[str, object]], change: str
) -> None:
    app, build = _app(tmp_path)
    cache = build / "CMakeCache.txt"
    text = cache.read_text(encoding="utf-8")
    if change == "missing":
        (build / "nsx-debug/context.json").unlink()
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
    with pytest.raises(NSXConfigError):
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
    for tool in ("cmake", "ninja"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} required for real CMake integration test")
    app = tmp_path / "legacy"
    app.mkdir()
    (app / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: my_custom_board\n"
    )
    build = app / "build/my_custom_board"
    from neuralspotx.operations._debug_settings import app_debug_settings

    # Configure actual packaged helper code with a host-only target: no SDK,
    # compiler, network, probe, or guessed Ninja command text is needed.
    helper = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake/nsx_helpers.cmake"
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
    result = app_debug_settings(app, board=None, build_dir=None)
    assert result.device == "BoardOverride"
    assert result.speed_khz == 750
    # A failed board switch updates CMake's requested NSX_BOARD but leaves
    # old generated files and device facts behind. Those facts must not be
    # attributed to the newly requested board.
    cmake.write_text(prefix + 'message(FATAL_ERROR "SDK unavailable")\n', encoding="utf-8")
    failed_cmd = [*cmd[:-1], "-DNSX_BOARD=apollo510_evb"]
    failed = subprocess.run(failed_cmd, capture_output=True, text=True)
    assert failed.returncode != 0
    with pytest.raises(NSXConfigError, match="selected board"):
        app_debug_settings(app, board="apollo510_evb", build_dir=build)
    assert len(reset_calls) == 0
    cmake.write_text(prefix + "nsx_add_segger_targets(demo)\n", encoding="utf-8")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    with pytest.raises(NSXConfigError, match="settings are missing"):
        app_debug_settings(app, board=None, build_dir=None)
    assert len(reset_calls) == 0


@pytest.mark.parametrize("as_path", [False, True])
def test_reset_expands_home_in_explicit_build_path(reset_calls, as_path):
    # Use a disposable directory under the real home to exercise expanduser on
    # every host without changing HOME/USERPROFILE or assuming drive layout.
    with tempfile.TemporaryDirectory(prefix="nsx-reset-path-", dir=Path.home()) as directory:
        app, build = _app(Path(directory))
        before = (build / "CMakeCache.txt").read_bytes()
        app_argument = Path("~") / app.relative_to(Path.home())
        build_argument = Path("~") / build.relative_to(Path.home())
        result = api.reset_target(
            app_dir=app_argument if as_path else str(app_argument),
            build_dir=build_argument if as_path else str(build_argument),
        )
        assert result.device == "CustomDevice" and result.probe_serial == "1234"
        assert len(reset_calls) == 1
        assert (build / "CMakeCache.txt").read_bytes() == before
