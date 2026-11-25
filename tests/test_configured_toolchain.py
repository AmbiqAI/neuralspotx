"""An explicit build toolchain must agree with the loaded CMake toolchain."""

from pathlib import Path

import pytest

from neuralspotx import api, cli
from neuralspotx._errors import NSXToolchainError
from neuralspotx.operations._debug_workflow import inspect_build


@pytest.fixture
def gcc_tree(tmp_path: Path) -> Path:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject: {name: demo}\nbaseline: none\n"
        "target: {board: apollo510_evb, soc: apollo510}\nmodules: []\n"
    )
    build = tmp_path / "build/apollo510_evb"
    records = build / "CMakeFiles/3.30.2"
    records.mkdir(parents=True)
    scripts = tmp_path / "cmake/nsx/toolchains"
    (records / "CMakeSystem.cmake").write_text(
        f'include("{(scripts / "arm-none-eabi-gcc.cmake").as_posix()}")\n'
    )
    gcc = tmp_path / "bin/arm-none-eabi-gcc"
    (records / "CMakeCCompiler.cmake").write_text(
        f'set(CMAKE_C_COMPILER "{gcc.as_posix()}")\nset(CMAKE_C_COMPILER_ID "GNU")\n'
    )
    # A later configure can overwrite the requested file while CMake retains GCC.
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_CACHEFILE_DIR:INTERNAL={build}\nCMAKE_HOME_DIRECTORY:INTERNAL={tmp_path}\n"
        "CMAKE_CACHE_MAJOR_VERSION:INTERNAL=3\nCMAKE_CACHE_MINOR_VERSION:INTERNAL=30\n"
        "CMAKE_CACHE_PATCH_VERSION:INTERNAL=2\nNSX_BOARD:STRING=apollo510_evb\n"
        f"CMAKE_TOOLCHAIN_FILE:FILEPATH={scripts / 'atfe.cmake'}\nARM_NONE_EABI_GCC:FILEPATH={gcc}\n"
    )
    return build


@pytest.mark.parametrize(
    "command", ["configure", "build", "flash", "view", "build-update", "flash-update"]
)
def test_reject_before_update_build_or_probe(
    gcc_tree: Path,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from neuralspotx.operations import _build

    def unexpected(*args, **kwargs):
        pytest.fail("updated, built or reached the probe after a toolchain mismatch")

    monkeypatch.setattr(api, "update_app", unexpected)
    monkeypatch.setattr(_build, "_run_build", unexpected)
    monkeypatch.setattr(_build.ProbeSelection, "resolve", unexpected)
    cmd, _, update = command.partition("-")
    args = [cmd, "--app-dir", str(gcc_tree.parent.parent), "--toolchain", "atfe"]
    if update:
        args.append("--update")
    assert cli.main(args) != 0
    message = capsys.readouterr().err
    assert all(word in message for word in ("atfe", "arm-none-eabi-gcc", "--build-dir"))


def test_compiler_facts_and_omitted_request(gcc_tree: Path) -> None:
    app = gcc_tree.parent.parent
    for gcc in ("gcc", "arm-none-eabi-gcc", " GCC "):
        inspect_build(app, gcc_tree, "apollo510_evb", toolchain=gcc)
    record = gcc_tree / "CMakeFiles/3.30.2/CMakeCCompiler.cmake"
    record.write_text('set(CMAKE_C_COMPILER "clang")\nset(CMAKE_C_COMPILER_ID "Clang")\n')
    inspect_build(app, gcc_tree, "apollo510_evb")
    with pytest.raises(NSXToolchainError, match="Clang"):
        inspect_build(app, gcc_tree, "apollo510_evb", toolchain="gcc")
