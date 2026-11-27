"""Exercise the app operation boundary without SEGGER tools or a physical probe."""

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from neuralspotx import (
    AppRttRequest,
    NSXConfigError,
    build_app,
    cli,
    create_board,
    flash_app,
    reset_target,
    resolve_rtt_app,
    tooling,
    view_app,
)
from neuralspotx.models import FlashResult
from neuralspotx.operations import _debug_backend as backend
from neuralspotx.operations._debug_workflow import OwnedBuild


class FixtureProgrammer:
    """Read an address emitted by the fixture's build and check the captured bytes."""

    def validate_probe(self, probe: backend.ProbeRequest) -> None:
        if probe.identity != "bench-A":
            raise NSXConfigError("Select the fixture with bench-A")

    def preflight(
        self, target: backend.DebugBuild, owned: OwnedBuild, *, same_configuration: bool
    ) -> None:
        pass  # The fixture needs no additional build configuration.

    def prepare(self, target: backend.DebugBuild) -> bool:
        return False

    @contextmanager
    def capture(self, target: backend.DebugBuild) -> Iterator[backend.PreparedFlash]:
        source = target.build / "image.bin"
        recipe = target.build / "load-address.txt"
        with TemporaryDirectory() as directory:
            private = Path(directory) / "image.bin"
            shutil.copyfile(source, private)
            image = backend.FlashImage(target.target, source, private, int(recipe.read_text(), 16))

            def program(image, probe, on_line):
                assert image.load_address == 0x4000
                assert image.captured != image.artifact
                assert probe.identity == "bench-A"
                assert image.captured.read_bytes() == b"fixture firmware"
                return FlashResult(image.target, image.artifact, recipe, probe.identity, True)

            yield backend.PreparedFlash(image, program)
        assert not private.exists()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if not shutil.which("cmake") or not shutil.which("ninja"):
        pytest.skip("host CMake and Ninja required")
    create_board("fixture", from_board="apollo510_evb", app_dir=tmp_path)
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject: {name: demo}\nbaseline: none\n"
        "target: {board: fixture, soc: apollo510}\n",
        encoding="utf-8",
    )
    (tmp_path / "image.in").write_bytes(b"fixture firmware")
    (tmp_path / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.20)\nset(CMAKE_TOOLCHAIN_FILE "" CACHE FILEPATH "" FORCE)\n'
        'project(demo NONE)\nfile(GENERATE OUTPUT "${CMAKE_BINARY_DIR}/load-address.txt" CONTENT "0x4000")\n'
        'add_custom_target(demo COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_SOURCE_DIR}/image.in" "${CMAKE_BINARY_DIR}/image.bin")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(tooling, "_list_jlink_inventory", lambda: pytest.fail("opened J-Link"))
    return tmp_path


def test_flash_only_programmer_at_api_and_cli(app, monkeypatch):
    tools = backend.DebugBackend("fixture programmer", flash=FixtureProgrammer())
    monkeypatch.setattr(backend, "for_board", lambda app, board: tools)
    result = flash_app(app, probe_serial="bench-A")
    assert result.target == "demo" and result.probe_serial == "bench-A"
    assert result.artifact.is_file() and result.recipe.is_file() and result.programming_verified
    assert cli.main(["flash", "--app-dir", str(app), "--probe-serial", "bench-A"]) == 0
    assert not (result.artifact.parent / "nsx-debug/context.json").exists()
    assert not list(result.artifact.parent.rglob("*.jlink"))
    with pytest.raises(NSXConfigError, match="SWO unavailable.*fixture"):
        view_app(app, probe_serial="bench-A")
    with pytest.raises(NSXConfigError, match="Reset unavailable.*fixture"):
        reset_target(app_dir=app, probe_serial="bench-A")
    with pytest.raises(NSXConfigError, match="RTT unavailable.*fixture"):
        resolve_rtt_app(AppRttRequest(app_dir=app, probe_serial="bench-A"))


def test_build_only_board(app, monkeypatch):
    monkeypatch.setattr(backend, "for_board", lambda app, board: backend.DebugBackend("build only"))
    with pytest.raises(NSXConfigError, match="Flash unavailable.*fixture"):
        flash_app(app)
    assert not (app / "build").exists()
    build_app(app)
    assert (app / "build" / "fixture" / "image.bin").is_file()
