"""Named-target flash and explicit J-Link reset contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import neuralspotx.cli as cli
from neuralspotx import NSXConfigError, NSXError
from neuralspotx._io import using_emitter
from neuralspotx.operations import _build, _hardware


def _flash_build(tmp_path: Path, target: str) -> tuple[Path, Path]:
    build_dir = tmp_path / "build with spaces"
    build_dir.mkdir()
    (build_dir / "build.ninja").write_text("# configured\n", encoding="utf-8")
    artifact = build_dir / f"{target}.bin"
    artifact.write_bytes(b"firmware")
    recipe = build_dir / "jlink" / target / "flash_cmds.jlink"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(f'LoadFile "{artifact}", 0x00410000\n', encoding="utf-8")
    return build_dir, artifact


def _stub_build_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, build_dir: Path) -> None:
    monkeypatch.setattr(
        _build,
        "_resolve_build_context",
        lambda *_args, **_kwargs: (tmp_path, "primary", "apollo510_evb", build_dir),
    )
    monkeypatch.setattr(_build, "warn_if_lock_stale", lambda *_args: None)
    monkeypatch.setattr(_build, "regenerate_active_board_glue", lambda *_args: None)
    monkeypatch.setattr(_build, "_ensure_app_modules", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(_build, "_run_cmake_configure", lambda *_args, **_kwargs: None)


def test_primary_flash_builds_and_validates_before_cmake_flash_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, artifact = _flash_build(tmp_path, "primary")
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout="Flash download: Total time needed: 0.2s\n", stderr=""
        )

    monkeypatch.setattr(_build, "run_capture", fake_capture)
    result = _build.flash_app_impl(tmp_path, probe_serial="1234")

    assert [cmd[4] for cmd in calls] == ["primary", "primary_flash"]
    assert result.target == "primary"
    assert result.artifact == artifact
    assert result.probe_serial == "1234"
    assert result.programming_verified is True


def test_named_flash_builds_then_uses_target_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, artifact = _flash_build(tmp_path, "hpx_profiler_power")
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        output = "Flash download: Total time needed: 0.2s\n" if cmd[4].endswith("_flash") else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr="")

    monkeypatch.setattr(_build, "run_capture", fake_capture)
    result = _build.flash_app_impl(tmp_path, target="hpx_profiler_power")

    assert [cmd[4] for cmd in calls] == ["hpx_profiler_power", "hpx_profiler_power_flash"]
    assert result.artifact == artifact
    assert result.recipe == build_dir / "jlink/hpx_profiler_power/flash_cmds.jlink"


def test_captured_flash_output_can_be_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    build_dir, _ = _flash_build(tmp_path, "primary")
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    monkeypatch.setattr(
        _build,
        "run_capture",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(
            cmd, 0, stdout="Flash download: Total time needed: 0.2s\n", stderr=""
        ),
    )
    with using_emitter(lambda _event: None):
        _build.flash_app_impl(tmp_path)
    assert capsys.readouterr() == ("", "")


def test_connection_only_ok_is_rejected() -> None:
    assert not _hardware.flash_programming_verified("Connecting to J-Link via USB...O.K.")


def test_recipe_must_load_selected_artifact(tmp_path: Path) -> None:
    build_dir, _ = _flash_build(tmp_path, "secondary")
    recipe = build_dir / "jlink/secondary/flash_cmds.jlink"
    recipe.write_text('LoadFile "wrong.bin", 0x00410000\n', encoding="utf-8")
    with pytest.raises(NSXConfigError, match="expected artifact"):
        _hardware.validate_flash_recipe(build_dir, "secondary")


def test_primary_flash_rejects_stale_recipe_before_programming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, _ = _flash_build(tmp_path, "primary")
    recipe = build_dir / "jlink/primary/flash_cmds.jlink"
    recipe.write_text('LoadFile "other.bin", 0x00410000\n', encoding="utf-8")
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(_build, "run_capture", fake_capture)
    with pytest.raises(NSXConfigError, match="expected artifact"):
        _build.flash_app_impl(tmp_path)

    assert [cmd[4] for cmd in calls] == ["primary"]


def test_flash_reconfigures_when_jlink_discovery_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, _ = _flash_build(tmp_path, "primary")
    (build_dir / "CMakeCache.txt").write_text(
        "NSX_JLINK_SERIAL:UNINITIALIZED=\n"
        "NSX_JLINK_EXE:FILEPATH=NSX_JLINK_EXE-NOTFOUND\n",
        encoding="utf-8",
    )
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    configure_calls: list[dict[str, object]] = []
    monkeypatch.setattr(_build, "find_segger_tool", lambda _names: "/opt/SEGGER/JLinkExe")
    monkeypatch.setattr(
        _build,
        "_run_cmake_configure",
        lambda *_args, **kwargs: configure_calls.append(kwargs),
    )
    monkeypatch.setattr(
        _build,
        "run_capture",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(
            cmd, 0, stdout="Flash download: Total time needed: 0.2s\n", stderr=""
        ),
    )

    _build.flash_app_impl(tmp_path)

    assert configure_calls == [{"toolchain": None, "probe_serial": None}]


def test_flash_reconfigures_to_clear_cached_probe_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, _ = _flash_build(tmp_path, "primary")
    (build_dir / "CMakeCache.txt").write_text(
        "NSX_JLINK_SERIAL:UNINITIALIZED=previous-probe\n"
        "NSX_JLINK_EXE:FILEPATH=/opt/SEGGER/JLinkExe\n",
        encoding="utf-8",
    )
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    configure_calls: list[dict[str, object]] = []
    monkeypatch.setattr(_build, "find_segger_tool", lambda _names: "/opt/SEGGER/JLinkExe")
    monkeypatch.setattr(
        _build,
        "_run_cmake_configure",
        lambda *_args, **kwargs: configure_calls.append(kwargs),
    )
    monkeypatch.setattr(
        _build,
        "run_capture",
        lambda cmd, **_kwargs: subprocess.CompletedProcess(
            cmd, 0, stdout="Flash download: Total time needed: 0.2s\n", stderr=""
        ),
    )

    result = _build.flash_app_impl(tmp_path)

    assert configure_calls == [{"toolchain": None, "probe_serial": None}]
    assert result.probe_serial is None


@pytest.mark.parametrize("missing", ["artifact", "recipe"])
def test_named_flash_fails_before_programming_when_input_is_missing(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_dir, artifact = _flash_build(tmp_path, "secondary")
    recipe = build_dir / "jlink/secondary/flash_cmds.jlink"
    (artifact if missing == "artifact" else recipe).unlink()
    _stub_build_context(monkeypatch, tmp_path, build_dir)
    calls: list[list[str]] = []

    def fake_capture(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(_build, "run_capture", fake_capture)
    with pytest.raises(NSXConfigError, match=missing):
        _build.flash_app_impl(tmp_path, target="secondary")
    assert [cmd[4] for cmd in calls] == ["secondary"]


@pytest.mark.parametrize("target", ["", ".", "..", "../escape", "nested/target", r"nested\\target"])
def test_flash_target_rejects_path_shapes(target: str) -> None:
    with pytest.raises(NSXConfigError):
        _hardware.validate_flash_target_name(target)


def test_debug_reset_returns_structured_result(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []

    def fake_run(script: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        scripts.append(script)
        return subprocess.CompletedProcess(["JLinkExe"], 0, stdout="", stderr="")

    monkeypatch.setattr(_hardware, "_run_jlink_script", fake_run)
    result = _hardware.reset_target_impl(
        device="Apollo330P_510L", probe_serial="1234", verify_reconnect=True
    )
    assert scripts == ["r\ng\nexit\n", "connect\nexit\n"]
    assert result.kind == "debug"
    assert result.reconnect_verified is True
    assert result.expected_disconnect is False


def test_swpoi_clean_exit_is_success_without_expected_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _hardware,
        "_run_jlink_script",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["JLinkExe"], 0, stdout="Writing 0000001B -> 40000004", stderr=""
        ),
    )
    result = _hardware.reset_target_impl(device="Apollo330P_510L", kind="swpoi")
    assert result.expected_disconnect is False
    assert result.reconnect_verified is None


def test_swpoi_accepts_only_expected_interrupted_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exc = subprocess.CalledProcessError(
        1,
        ["JLinkExe"],
        output="w4 40000004 1b\nCould not write memory at 40000004",
        stderr="",
    )
    monkeypatch.setattr(
        _hardware, "_run_jlink_script", lambda *_args, **_kwargs: (_ for _ in ()).throw(exc)
    )
    result = _hardware.reset_target_impl(device="Apollo330P_510L", kind="swpoi")
    assert result.expected_disconnect is True


def test_swpoi_expected_disconnect_and_reconnect_through_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the interrupted-write path across the real subprocess boundary."""

    fake_jlink = tmp_path / "fake_jlink.py"
    fake_jlink.write_text(
        """\
from pathlib import Path
import sys

script = Path(sys.argv[1]).read_text(encoding="utf-8")
if not script.startswith("ExitOnError 1\\n"):
    print("Missing ExitOnError 1", file=sys.stderr)
    raise SystemExit(3)
if "w4 40000004 1b" in script:
    print("J-Link>w4 40000004 1b")
    print("Could not write memory at 40000004", file=sys.stderr)
    raise SystemExit(1)
if script == "ExitOnError 1\\nconnect\\nexit\\n":
    print("Connecting to target via SWD...O.K.")
    raise SystemExit(0)
print("Unexpected command file", file=sys.stderr)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    command_files: list[Path] = []

    def fake_jlink_command(
        *,
        device: str,
        interface: str,
        speed_khz: int,
        probe_serial: str | None,
        command_file: Path,
    ) -> list[str]:
        assert device == "AMA3B2KK-KBR"
        assert interface == "SWD"
        assert speed_khz == 4000
        assert probe_serial == "1234567890"
        command_files.append(command_file)
        return [sys.executable, str(fake_jlink), str(command_file)]

    monkeypatch.setattr(_hardware, "_jlink_command", fake_jlink_command)

    result = _hardware.reset_target_impl(
        device="AMA3B2KK-KBR",
        probe_serial="1234567890",
        kind="swpoi",
        verify_reconnect=True,
    )

    assert result.expected_disconnect is True
    assert result.reconnect_verified is True
    assert len(command_files) == 2
    assert all(not command_file.exists() for command_file in command_files)


@pytest.mark.parametrize(
    "output",
    [
        "Cannot connect to J-Link via USB",
        "w4 40000004 1b\nCannot connect to target",
        "Could not write memory at 20000000",
        "w4 40000004 1b\nUnknown command",
    ],
)
def test_swpoi_rejects_unrelated_nonzero(output: str, monkeypatch: pytest.MonkeyPatch) -> None:
    exc = subprocess.CalledProcessError(1, ["JLinkExe"], output=output, stderr="")
    monkeypatch.setattr(
        _hardware, "_run_jlink_script", lambda *_args, **_kwargs: (_ for _ in ()).throw(exc)
    )
    with pytest.raises(NSXError):
        _hardware.reset_target_impl(device="Apollo330P_510L", kind="swpoi")


def test_reconnect_failure_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(1, ["JLinkExe"], output="offline", stderr="")
        return subprocess.CompletedProcess(["JLinkExe"], 0, stdout="", stderr="")

    monkeypatch.setattr(_hardware, "_run_jlink_script", fake_run)
    with pytest.raises(NSXError, match="reconnect verification"):
        _hardware.reset_target_impl(device="Apollo330P_510L", kind="debug", verify_reconnect=True)


def test_cli_flash_threads_named_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: app\ntarget:\n  board: apollo510_evb\nmodules: []\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        cli.api,
        "flash_app",
        lambda app_dir, **kwargs: captured.update({"app_dir": app_dir, **kwargs}),
    )
    assert cli.main(["flash", "--app-dir", str(tmp_path), "--target", "secondary"]) == 0
    assert captured["target"] == "secondary"


def test_cli_reset_threads_explicit_mechanism(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli.api, "reset_target", lambda **kwargs: captured.update(kwargs))
    assert (
        cli.main([
            "reset",
            "--device",
            "Apollo330P_510L",
            "--kind",
            "swpoi",
            "--probe-serial",
            "1234",
            "--verify-reconnect",
        ])
        == 0
    )
    assert captured["kind"] == "swpoi"
    assert captured["probe_serial"] == "1234"
    assert captured["verify_reconnect"] is True
