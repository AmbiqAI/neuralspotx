"""RTT resolution uses real ELF/CMake facts; capture tests never access USB."""

from __future__ import annotations

import errno
import io
import json
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from debug_fixtures import cmake, make_debug_app, prepare

from neuralspotx import AppRttRequest, NSXConfigError, NSXError, RttResult, api, cli
from neuralspotx import _rtt_capture as runtime
from neuralspotx.models import RttSettings
from neuralspotx.operations import _rtt


def capture_runtime(
    settings: RttSettings,
    *,
    duration_s: float,
    startup_timeout_s: float,
    capture: Path | None = None,
    on_data=None,
) -> RttResult:
    return runtime.capture_rtt(
        settings,
        duration_s=duration_s,
        startup_timeout_s=startup_timeout_s,
        capture=capture,
        on_data=on_data,
    )


@pytest.fixture
def app(tmp_path: Path) -> tuple[Path, Path]:
    return make_debug_app(tmp_path / "app with spaces", "custom")


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
    with (root / "nsx.yml").open("a") as stream:
        stream.write("console:\n  transport: swo\n")
    from neuralspotx.operations._debug_context import load_debug_context

    produced = load_debug_context(root, build, "custom").target().elf
    shutil.copyfile(elf, produced)
    elf = produced
    monkeypatch.setattr(runtime, "_worker_command", lambda *_: pytest.fail("offline opened worker"))
    settings = api.resolve_rtt_app(AppRttRequest(root))
    assert settings.elf == elf
    assert settings.address > 0
    assert settings.device == "CustomDevice"
    assert settings.probe_serial == "1234"
    assert cli.main(["rtt", str(root), "--print-settings", "--probe-serial", "5678"]) == 0
    captured = capsys.readouterr()
    assert "Primary console" in captured.err
    output = json.loads(captured.out)
    assert output["probe_serial"] == "5678"
    assert output["elf"] == str(elf)
    assert output["address"] == settings.address


def test_missing_pointer_requests_configuration(app: tuple[Path, Path]) -> None:
    (app[1] / "nsx-debug/context.json").unlink()
    with pytest.raises(NSXConfigError, match="prepar"):
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
    result = capture_runtime(
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
        capture_runtime(settings, duration_s=0.1, startup_timeout_s=0.5)
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
        capture_runtime(settings, duration_s=0.1, startup_timeout_s=2, capture=output, on_data=fail)
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
        capture_runtime(settings, duration_s=1, startup_timeout_s=1, capture=settings.elf)
    output = settings.app_dir / "existing"
    output.write_bytes(b"keep")
    with pytest.raises(NSXConfigError, match="Choose a new file"):
        capture_runtime(settings, duration_s=1, startup_timeout_s=1, capture=output)
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

    def execute(
        settings: RttSettings,
        *,
        probe_serial: str | None = None,
        discover_probe: bool = False,
        **kwargs,
    ):
        return capture_runtime(settings, **kwargs)

    monkeypatch.setattr(operations, "rtt_app_impl", execute)
    worker(monkeypatch, "print('ready\\t5678'); print('done\\t')")
    result = api.rtt_app(AppRttRequest(settings.app_dir, duration_s=0.1))
    assert result.settings == replace(settings, probe_serial="5678")
    assert result.bytes_received == 0


def test_real_cmake_resolves_nested_renamed_executable(tmp_path: Path) -> None:
    if sys.platform != "linux":
        pytest.skip("Linux ELF host fixture")
    root, build = make_debug_app(tmp_path / "cmake app", "custom")
    project = root / "CMakeLists.txt"
    with project.open("a") as stream:
        stream.write(
            'set_target_properties(demo PROPERTIES OUTPUT_NAME "renamed app" SUFFIX ".axf" RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/nested")\n'
        )
    prepare(root, build)
    cmake("--build", build)
    result = api.resolve_rtt_app(AppRttRequest(root, build_dir=build))
    assert result.elf == build / "nested/renamed app.axf"
    assert result.address > 0
    stale = build / "nsx-artifacts/removed.path"
    stale.write_text(str(result.elf) + "\n")
    cmake("-S", root, "-B", build)
    assert not stale.exists()
    # Ordinary configure invalidates context even if an old ELF remains.
    assert result.elf.exists()
    with pytest.raises(NSXConfigError, match="prepar"):
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
        capture_runtime(settings, duration_s=0.1, startup_timeout_s=2, on_data=fail)
    assert caught.value is failure


def test_protocol_accepts_crlf(settings: RttSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    worker(
        monkeypatch,
        "import sys; sys.stdout.buffer.write(b'ready\\t1234\\r\\ndata\\tAP8=\\r\\ndone\\t\\r\\n')",
    )
    result = capture_runtime(settings, duration_s=0.1, startup_timeout_s=2)
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

    def execute(
        settings: RttSettings,
        *,
        probe_serial: str | None = None,
        discover_probe: bool = False,
        **kwargs,
    ):
        return capture_runtime(settings, **kwargs)

    monkeypatch.setattr(operations, "rtt_app_impl", execute)
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


def test_disk_full_flush_does_not_mask_capture_error(
    settings: RttSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FullDisk(io.RawIOBase):
        def writable(self) -> bool:
            return True

        def write(self, data) -> int:
            raise OSError(errno.ENOSPC, "No space left on device")

    # The standard buffer really retries its failed flush during close.
    sink = io.BufferedWriter(FullDisk())
    destination = settings.app_dir / "full.bin"
    original_open = Path.open

    def open_capture(path: Path, *args, **kwargs):
        return sink if path == destination else original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_capture)
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tYQ=='); import time; time.sleep(30)")
    with pytest.raises(NSXError, match="RTT file write failed"):
        capture_runtime(settings, duration_s=0.1, startup_timeout_s=2, capture=destination)
    assert sink.closed


@pytest.mark.parametrize(
    "callback_failure", [None, RuntimeError("callback failed"), KeyboardInterrupt()]
)
def test_close_failure_preserves_pending_exception(
    settings: RttSettings,
    monkeypatch: pytest.MonkeyPatch,
    callback_failure: BaseException | None,
) -> None:
    class BadClose(io.BytesIO):
        def close(self) -> None:
            super().close()
            raise OSError("close failed")

    sink = BadClose()
    destination = settings.app_dir / "close.bin"
    original_open = Path.open

    def open_capture(path: Path, *args, **kwargs):
        return sink if path == destination else original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_capture)
    worker(monkeypatch, "print('ready\\t1234'); print('data\\tYQ=='); print('done\\t')")

    def callback(_: bytes) -> None:
        if callback_failure is not None:
            raise callback_failure

    if callback_failure is not None:
        with pytest.raises(type(callback_failure)) as caught:
            capture_runtime(
                settings, duration_s=0.1, startup_timeout_s=2, capture=destination, on_data=callback
            )
        assert caught.value is callback_failure
    else:
        with pytest.raises(NSXError, match="RTT file close failed"):
            capture_runtime(
                settings, duration_s=0.1, startup_timeout_s=2, capture=destination, on_data=callback
            )
    assert sink.closed
    if callback_failure is None:
        # An exception handled by the caller is not a capture failure. It must
        # not suppress a new close error from an otherwise successful capture.
        sink = BadClose()
        try:
            raise ValueError("handled by caller")
        except ValueError:
            with pytest.raises(NSXError, match="RTT file close failed"):
                capture_runtime(
                    settings,
                    duration_s=0.1,
                    startup_timeout_s=2,
                    capture=destination,
                    on_data=callback,
                )
        assert sink.closed
