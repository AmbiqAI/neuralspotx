"""Runner contract exercised without Arm software or network access."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from neuralspotx import AppRunRequest, NSXConfigError, NSXTimeoutError, NSXToolchainError, run_app
from neuralspotx.cli import main
from neuralspotx.operations import _run

BOARD = "corstone300_fvp_u55"
PASS = b"hello\r\nApplication exit code: 0.\r\n\x04"
FAIL = b"assert failed\nApplication exit code: -7.\n\x04\nEXITTHESIM\n"


@pytest.fixture
def app(tmp_path: Path) -> Path:
    (tmp_path / "nsx.yml").write_text(
        f"schema_version: 2\nproject:\n  name: demo\ntarget:\n  board: {BOARD}\n  soc: corstone300\n"
    )
    build = tmp_path / "build" / BOARD
    build.mkdir(parents=True)
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={tmp_path.as_posix()}\n"
        f"CMAKE_CACHEFILE_DIR:INTERNAL={build.as_posix()}\nNSX_BOARD:STRING={BOARD}\n"
    )
    (build / "demo").write_bytes(b"\x7fELF\x01\x01" + bytes(10) + b"\x02\x00\x28\x00")
    return tmp_path


def fake_model(monkeypatch, uart: bytes, *, error: BaseException | None = None):
    def launch(command, *, cwd, timeout, output):
        assert command[0] == str(Path(sys.executable).resolve())
        assert command[-2] == "-a" and Path(command[-1]).name == "demo"
        assert "mps3_board.uart0.shutdown_on_eot=1" in command
        assert timeout == 30
        output.write(b"model diagnostic\n")
        (cwd / "uart.log").write_bytes(uart)
        if error:
            raise error

    monkeypatch.setattr(_run, "run", launch)


def test_api_retains_separate_guest_and_model_logs_per_run(app, monkeypatch) -> None:
    request = AppRunRequest(app_dir=app, fvp=sys.executable)
    for payload, expected in [(PASS, 0), (FAIL, -7)]:
        fake_model(monkeypatch, payload)
        result = run_app(request)
        assert result.guest_exit_code == expected
        assert result.uart_log.read_bytes() == payload
        assert result.model_log.read_bytes() == b"model diagnostic\n"
    assert len(list((app / "build" / BOARD / "nsx-run").iterdir())) == 2


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        PASS[:-1],
        PASS + b"trailing",
        PASS + b"\n" + FAIL,
        b"Application exit code: 2147483648.\n\x04",
    ],
)
def test_incomplete_or_conflicting_guest_evidence(app, monkeypatch, payload) -> None:
    fake_model(monkeypatch, payload)
    with pytest.raises(NSXToolchainError, match="guest exit record"):
        run_app(AppRunRequest(app_dir=app, fvp=sys.executable))


@pytest.mark.parametrize(
    ("error", "exception"),
    [
        (subprocess.TimeoutExpired("FVP", 30), NSXTimeoutError),
        (subprocess.CalledProcessError(7, "FVP"), NSXToolchainError),
    ],
)
def test_model_failure_takes_precedence_and_preserves_output(
    app, monkeypatch, error, exception
) -> None:
    fake_model(monkeypatch, PASS, error=error)
    with pytest.raises(exception, match="Run logs:"):
        run_app(AppRunRequest(app_dir=app, fvp=sys.executable))
    assert next(app.rglob("uart.log")).read_bytes() == PASS


@pytest.mark.parametrize(("payload", "status"), [(PASS, 0), (FAIL, 1), (b"no terminator", 2)])
def test_cli_reports_guest_and_infrastructure_outcomes(
    app, monkeypatch, capsysbinary, payload, status
) -> None:
    fake_model(monkeypatch, payload)
    assert main(["run", str(app), "--fvp", sys.executable]) == status
    stdout, stderr = capsysbinary.readouterr()
    if status != 2:
        assert stdout == payload and b"Run logs:" in stderr
    else:
        assert b"guest exit record" in stderr


def test_refuses_wrong_build_owner_and_escaping_elf(app) -> None:
    request = AppRunRequest(app_dir=app, fvp=sys.executable, elf="../../nsx.yml")
    with pytest.raises(NSXConfigError, match="inside"):
        run_app(request)
    cache = app / "build" / BOARD / "CMakeCache.txt"
    cache.write_text(
        cache.read_text().replace(f"NSX_BOARD:STRING={BOARD}", "NSX_BOARD:STRING=apollo510_evb")
    )
    with pytest.raises(NSXConfigError, match="board mismatch"):
        run_app(request)
