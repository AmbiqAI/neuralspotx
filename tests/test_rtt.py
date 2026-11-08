"""RTT resolution uses real ELF/CMake facts; capture tests never access USB."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from neuralspotx import AppRttRequest, NSXConfigError, NSXError, RttResult, api, cli
from neuralspotx import _rtt_capture as runtime
from neuralspotx.models import RttSettings
from neuralspotx.operations import _rtt


@pytest.fixture
def app(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "app with spaces"
    build = root / "build" / "custom"
    build.mkdir(parents=True)
    (root / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: custom\n"
    )
    (build / "build.ninja").touch()
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={root.as_posix()}\nNSX_BOARD:STRING=custom\n"
        "NSX_RESET_BOARD:INTERNAL=custom\nNSX_RESET_DEVICE:INTERNAL=TestDevice\n"
        "NSX_RESET_SPEED_KHZ:INTERNAL=1200\nNSX_JLINK_SERIAL:STRING=1234\n"
    )
    return root, build


@pytest.fixture
def elf(tmp_path: Path) -> Path:
    cc = shutil.which("cc")
    if not cc or sys.platform != "linux":
        pytest.skip("Linux ELF host C compiler needed for this fixture")
    source = tmp_path / "fixture.c"
    source.write_text("unsigned char _SEGGER_RTT[1024]; int main(void) {return _SEGGER_RTT[0];}\n")
    output = tmp_path / "actual output.axf"
    subprocess.run([cc, "-no-pie", str(source), "-o", str(output)], check=True, capture_output=True)
    return output


def test_resolve_exact_artifact_and_offline_cli(
    app: tuple[Path, Path],
    elf: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, build = app
    (build / "nsx-artifacts").mkdir()
    (build / "nsx-artifacts/demo.path").write_text(str(elf) + "\n")
    monkeypatch.setattr(runtime, "_worker_command", lambda *_: pytest.fail("offline opened worker"))
    settings = api.resolve_rtt_app(AppRttRequest(root))
    assert settings.elf == elf
    assert settings.address > 0
    assert settings.device == "TestDevice"
    assert settings.probe_serial == "1234"
    assert cli.main(["rtt", str(root), "--print-settings", "--probe-serial", "5678"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["probe_serial"] == "5678"
    assert output["elf"] == str(elf)
    assert output["address"] == settings.address


def test_missing_pointer_requests_configuration(app: tuple[Path, Path]) -> None:
    with pytest.raises(NSXConfigError, match="nsx configure"):
        api.resolve_rtt_app(AppRttRequest(app[0]))


@pytest.mark.parametrize("serial", ["0", "", "-1", "abc", "１２３"])
def test_invalid_serial_before_worker(app: tuple[Path, Path], serial: str) -> None:
    with pytest.raises(NSXConfigError, match="serial"):
        api.resolve_rtt_app(AppRttRequest(app[0], probe_serial=serial))


def test_missing_and_malformed_elf(tmp_path: Path) -> None:
    with pytest.raises(NSXConfigError, match="nsx build"):
        _rtt._rtt_address(tmp_path / "missing")
    bad = tmp_path / "bad"
    bad.write_bytes(b"not an ELF")
    with pytest.raises(NSXConfigError, match="Cannot read RTT ELF"):
        _rtt._rtt_address(bad)


def test_stripped_elf_rejected(elf: Path) -> None:
    strip = shutil.which("strip")
    if not strip:
        pytest.skip("strip not installed")
    subprocess.run([strip, "--strip-all", str(elf)], check=True, capture_output=True)
    with pytest.raises(NSXConfigError, match="unstripped"):
        _rtt._rtt_address(elf)


@pytest.fixture
def settings(tmp_path: Path) -> RttSettings:
    executable = tmp_path / "app.axf"
    executable.write_bytes(b"immutable executable")
    return RttSettings(
        tmp_path, "custom", tmp_path, "demo", executable, 0x20001000, "TestDevice", 4000, "1234"
    )


def worker(monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    monkeypatch.setattr(runtime, "_worker_command", lambda *_: [sys.executable, "-u", "-c", body])


def test_exact_bytes_and_result(settings: RttSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tAP9hDQo='); print('done\\t')")
    received: list[bytes] = []
    output = settings.app_dir / "capture.bin"
    result = _rtt.rtt_app_impl(
        settings, duration_s=0.1, startup_timeout_s=2, capture=output, on_data=received.append
    )
    assert b"".join(received) == b"\x00\xffa\r\n"
    assert output.read_bytes() == b"\x00\xffa\r\n"
    assert result.bytes_received == 5
    assert result.settings.probe_serial == "1234"


@pytest.mark.parametrize(
    "body,match",
    [
        ("import time; time.sleep(30)", "startup"),
        ("print('ready\\t1234'); import time; time.sleep(30)", "capture/shutdown"),
        ("print('ready\\t1234'); print('error\\tcmVhZCBmYWlsZWQ=')", "read failed"),
        ("print('ready\\t1234')", "without completing"),
        ("print('data\\tYQ==')", "Unexpected"),
        ("print('x'*9000)", "Invalid"),
    ],
)
def test_worker_failures_are_bounded(
    settings: RttSettings,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    match: str,
) -> None:
    worker(monkeypatch, body)
    monkeypatch.setattr(runtime, "_SHUTDOWN_GRACE_S", 0.1)
    started = time.monotonic()
    with pytest.raises(NSXError, match=match):
        _rtt.rtt_app_impl(settings, duration_s=0.1, startup_timeout_s=0.5)
    assert time.monotonic() - started < 5


def test_callback_failure_cleans_worker_and_preserves_file(
    settings: RttSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tYQ=='); import time; time.sleep(30)")
    output = settings.app_dir / "partial.bin"

    def fail(_: bytes) -> None:
        raise RuntimeError("caller failure")

    with pytest.raises(RuntimeError, match="caller failure"):
        _rtt.rtt_app_impl(
            settings, duration_s=0.1, startup_timeout_s=2, capture=output, on_data=fail
        )
    assert output.read_bytes() == b"a"
    # Cleanup closes the file, including on Windows where unlink would otherwise fail.
    output.unlink()


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_timing_validation(settings: RttSettings, value: float) -> None:
    with pytest.raises(NSXConfigError, match="finite"):
        _rtt.rtt_app_impl(settings, duration_s=value, startup_timeout_s=1)
    with pytest.raises(NSXConfigError, match="finite"):
        _rtt.rtt_app_impl(settings, duration_s=1, startup_timeout_s=value)


def test_existing_capture_is_preserved(settings: RttSettings) -> None:
    with pytest.raises(NSXConfigError, match="overwrite"):
        _rtt.rtt_app_impl(settings, duration_s=1, startup_timeout_s=1, capture=settings.elf)
    output = settings.app_dir / "existing"
    output.write_bytes(b"keep")
    with pytest.raises(NSXConfigError, match="Choose a new file"):
        _rtt.rtt_app_impl(settings, duration_s=1, startup_timeout_s=1, capture=output)
    assert output.read_bytes() == b"keep"


def test_cli_incremental_utf8(
    settings: RttSettings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from neuralspotx.cli import _cmd_rtt

    monkeypatch.setattr(_cmd_rtt, "resolve_app_dir", lambda _: settings.app_dir)

    def capture(request: AppRttRequest, *, on_data):
        assert request.duration_s == 3
        on_data(b"\xe2")
        on_data(b"\x82\xac\n")
        return RttResult(settings, 4, None)

    monkeypatch.setattr(api, "rtt_app", capture)
    assert cli.main(["rtt", "--duration", "3"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "€\n"
    assert "4 bytes" in captured.err


def test_api_dispatch(settings: RttSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    from neuralspotx import operations

    monkeypatch.setattr(operations, "resolve_rtt_app_impl", lambda *_, **__: settings)
    worker(monkeypatch, "print('ready\\t5678'); print('done\\t')")
    result = api.rtt_app(AppRttRequest(settings.app_dir, duration_s=0.1))
    assert result.settings == replace(settings, probe_serial="5678")
    assert result.bytes_received == 0


def test_real_cmake_resolves_nested_renamed_executable(tmp_path: Path) -> None:
    for tool in ("cmake", "ninja", "cc"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} needed for host-only CMake fixture")
    if sys.platform != "linux":
        pytest.skip("fixture requires a Linux ELF host compiler")
    root = tmp_path / "cmake app"
    nested = root / "nested"
    nested.mkdir(parents=True)
    build = root / "build"
    helper = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake/nsx_helpers.cmake"
    (root / "nsx.yml").write_text(
        "schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: custom\n"
    )
    (root / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(demo C)\n"
        'set(NSX_BOARD custom CACHE STRING "")\n'
        "set(NSX_SEGGER_DEVICE TestDevice)\nset(NSX_SEGGER_IF_SPEED 4000)\n"
        f'include("{helper.as_posix()}")\nadd_subdirectory(nested)\n'
    )
    (nested / "main.c").write_text("unsigned char _SEGGER_RTT[256]; int main(void){return 0;}\n")
    (nested / "CMakeLists.txt").write_text(
        "add_executable(demo main.c)\ntarget_link_options(demo PRIVATE -no-pie)\n"
        'set_target_properties(demo PROPERTIES OUTPUT_NAME "renamed app" SUFFIX ".axf")\n'
        "nsx_add_segger_targets(demo)\n"
    )
    subprocess.run(
        ["cmake", "-G", "Ninja", "-S", str(root), "-B", str(build)], check=True, capture_output=True
    )
    subprocess.run(["cmake", "--build", str(build)], check=True, capture_output=True)
    result = api.resolve_rtt_app(AppRttRequest(root, build_dir=build))
    assert result.elf == build / "nested/renamed app.axf"
    assert result.address > 0
    stale = build / "nsx-artifacts/removed.path"
    stale.write_text(str(result.elf) + "\n")
    subprocess.run(["cmake", "-S", str(root), "-B", str(build)], check=True, capture_output=True)
    assert not stale.exists()
    # Keep the old ELF on disk, but remove the last registered target.
    (nested / "CMakeLists.txt").write_text("# no executable targets\n")
    subprocess.run(["cmake", "-S", str(root), "-B", str(build)], check=True, capture_output=True)
    assert result.elf.exists()
    with pytest.raises(NSXConfigError, match="nsx configure"):
        api.resolve_rtt_app(AppRttRequest(root, build_dir=build))


@pytest.fixture(autouse=True)
def assert_workers_reaped(monkeypatch: pytest.MonkeyPatch):
    original = runtime._start_child
    children: list[subprocess.Popen] = []

    def track(*args, **kwargs):
        proc = original(*args, **kwargs)
        children.append(proc)
        return proc

    monkeypatch.setattr(runtime, "_start_child", track)
    yield
    for proc in children:
        assert proc.poll() is not None, "RTT worker leaked after operation"
        assert proc.stdout is not None and proc.stdout.closed


@pytest.mark.parametrize("failure", [OSError("disk"), UnicodeError("encoding")])
def test_callback_exception_identity(
    settings: RttSettings, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tYQ=='); import time; time.sleep(30)")

    def fail(_: bytes) -> None:
        raise failure

    with pytest.raises(type(failure)) as caught:
        _rtt.rtt_app_impl(settings, duration_s=0.1, startup_timeout_s=2, on_data=fail)
    assert caught.value is failure


def test_protocol_accepts_crlf(settings: RttSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    worker(
        monkeypatch,
        "import sys; sys.stdout.buffer.write(b'ready\\t1234\\r\\ndata\\tAP8=\\r\\ndone\\t\\r\\n')",
    )
    result = _rtt.rtt_app_impl(settings, duration_s=0.1, startup_timeout_s=2)
    assert result.bytes_received == 2


@pytest.mark.parametrize("encoding", ["ascii", "cp1252"])
def test_cli_unencodable_stdout_preserves_raw_capture(
    settings: RttSettings,
    monkeypatch: pytest.MonkeyPatch,
    encoding: str,
) -> None:
    from neuralspotx import operations
    from neuralspotx.cli import _cmd_rtt

    monkeypatch.setattr(_cmd_rtt, "resolve_app_dir", lambda _: settings.app_dir)
    monkeypatch.setattr(operations, "resolve_rtt_app_impl", lambda *_, **__: settings)
    # Invalid UTF-8 plus an incomplete trailing sequence exercises both writes
    # and decoder finalization. The binary file must retain all original bytes.
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tYWJj/+I='); print('done\\t')")
    raw = io.BytesIO()
    terminal = io.TextIOWrapper(raw, encoding=encoding, errors="strict")
    monkeypatch.setattr(sys, "stdout", terminal)
    capture = settings.app_dir / "raw.bin"
    assert cli.main(["rtt", "--file", str(capture), "--duration", ".1"]) == 0
    terminal.flush()
    assert raw.getvalue() == b"abc??"
    assert capture.read_bytes() == b"abc\xff\xe2"
