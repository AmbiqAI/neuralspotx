"""Configure/build failures at the public boundary, using host CMake and Ninja."""

import shutil
import subprocess
from pathlib import Path

import pytest

from neuralspotx import NSXError, NSXTimeoutError, NSXToolchainError, build_app, configure_app
from neuralspotx.cli import main


@pytest.fixture
def app(tmp_path: Path) -> Path:
    if not shutil.which("cmake") or not shutil.which("ninja"):
        pytest.skip("host CMake and Ninja required")
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject: {name: demo}\nbaseline: none\n"
        "targets: {default: apollo510_evb, supported: [apollo510_evb]}\n"
    )
    toolchain = tmp_path / "cmake/nsx/toolchains/arm-none-eabi-gcc.cmake"
    toolchain.parent.mkdir(parents=True)
    toolchain.write_text("# Host-only project with no compiler.\n")
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(demo NONE)\n"
        "add_custom_target(demo COMMAND ${CMAKE_COMMAND} -E echo success)\n"
        'add_custom_target(broken COMMAND ${CMAKE_COMMAND} -P "${CMAKE_SOURCE_DIR}/fail.cmake")\n'
        "add_custom_target(slow COMMAND ${CMAKE_COMMAND} -E sleep 15)\n"
    )
    (tmp_path / "fail.cmake").write_text('message(FATAL_ERROR "fixture build diagnostic")\n')
    return tmp_path


@pytest.mark.parametrize("call", [configure_app, build_app])
def test_configure_failure(app, call):
    with (app / "CMakeLists.txt").open("a") as f:
        f.write('message(FATAL_ERROR "fixture configure diagnostic")\n')
    with pytest.raises(NSXToolchainError, match="CMake configure") as error:
        call(app)
    cause = error.value.__cause__
    assert isinstance(cause, subprocess.CalledProcessError)
    assert cause.cmd[:2] == ["cmake", "-S"]
    assert cause.returncode != 0
    assert "fixture configure diagnostic" in cause.stderr
    assert "fixture configure diagnostic" in str(error.value)


@pytest.mark.parametrize("stream", [False, True])
def test_build_error_and_success(app, stream):
    lines = []
    on_line = lines.append if stream else None
    build_app(app, on_line=on_line)
    if stream:
        assert "success" in lines
    with pytest.raises(NSXError, match="fixture build diagnostic") as error:
        build_app(app, target="broken", on_line=on_line)
    assert isinstance(error.value, NSXToolchainError)
    cause = error.value.__cause__
    assert isinstance(cause, subprocess.CalledProcessError)
    assert cause.cmd[:2] == ["cmake", "--build"] and "broken" in cause.cmd
    assert f"exit code {cause.returncode}" in str(error.value)
    if stream:
        assert any("fixture build diagnostic" in line for line in lines)


@pytest.mark.parametrize(
    "error",
    [subprocess.CalledProcessError(3, "consumer"), subprocess.TimeoutExpired("consumer", 5)],
)
def test_build_callback_propagates_original_exception(app, error):
    def fail(_line):
        raise error

    with pytest.raises(type(error)) as raised:
        build_app(app, on_line=fail)
    assert raised.value is error


def test_build_timeout(app):
    configure_app(app)
    with pytest.raises(NSXTimeoutError) as raised:
        build_app(app, target="slow", timeout_s=0.5)
    assert raised.value.timeout_s == 0.5
    assert "slow" in (raised.value.command or "")


def test_cli_build_failure(app, capsys):
    assert main(["build", "--app-dir", str(app), "--target", "broken"]) == 1
    stderr = capsys.readouterr().err
    assert "CMake build failed with exit code" in stderr
    assert "fixture build diagnostic" in stderr
    assert "Traceback" not in stderr


def test_emitter_timeout_is_caller_owned(app):
    error = subprocess.TimeoutExpired("reporter", 10)

    def emit(_event):
        raise error

    with pytest.raises(subprocess.TimeoutExpired) as raised:
        configure_app(app, emit=emit)
    assert raised.value is error
