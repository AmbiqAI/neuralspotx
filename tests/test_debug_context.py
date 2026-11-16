"""Host-only protocol tests with real CMake and a tiny native executable."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from neuralspotx._errors import NSXConfigError
from neuralspotx.operations._debug_context import capture_debug_context, load_debug_context

CMAKE_ROOT = Path(__file__).parents[1] / "src/neuralspotx/cmake"


def run(*args: str | Path, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, timeout=45)
    if ok:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture
def project(tmp_path: Path) -> tuple[Path, Path, Path]:
    cmake = shutil.which("cmake")
    if not cmake or not shutil.which("ninja") or not (shutil.which("cc") or shutil.which("cl")):
        pytest.skip("native CMake/Ninja/C compiler required")
    version = run(cmake, "--version").stdout.split()[2]
    if tuple(map(int, version.split(".")[:2])) < (3, 31):
        pytest.skip("opt-in debug handoff requires CMake >=3.31")
    source, build = tmp_path / "app space", tmp_path / "build space"
    source.mkdir()
    helpers = source / "cmake"
    shutil.copytree(CMAKE_ROOT, helpers)
    (source / "main.c").write_text("int main(void) {return 0;}\n", encoding="utf-8")
    (source / "board.cmake").write_text('set(NSX_SEGGER_DEVICE "device-A")\n', encoding="utf-8")
    (source / "members").mkdir()
    (source / "members/one").write_text("x", encoding="utf-8")
    (source / "external.txt").write_text("device-A", encoding="utf-8")
    (source / "sub").mkdir()
    (source / "sub/CMakeLists.txt").write_text(
        """
add_executable(app ../main.c)
set_target_properties(app PROPERTIES OUTPUT_NAME renamed SUFFIX .custom)
add_custom_command(TARGET app POST_BUILD
  COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:app> $<TARGET_FILE_DIR:app>/app.bin)
nsx_add_segger_targets(app)
""",
        encoding="utf-8",
    )
    (source / "CMakeLists.txt").write_text(
        """cmake_minimum_required(VERSION 3.24)
project(context_fixture C)
set(NSX_BOARD fixture)
set(NSX_SEGGER_IF_SPEED 4000)
set(NSX_SEGGER_PF_ADDR 0x1000)
set(NSX_SEGGER_CPUFREQ 96000000)
set(NSX_SEGGER_SWOFREQ 1000000)
set(NSX_CMAKE_DIR "${CMAKE_SOURCE_DIR}/cmake")
# Never discover or invoke a real probe tool in this fixture.
set(NSX_JLINK_EXE "${CMAKE_COMMAND}")
set(NSX_JLINK_SWO_EXE "${CMAKE_COMMAND}")
include(cmake/nsx_helpers.cmake)
include(board.cmake)
if(EXISTS "${CMAKE_SOURCE_DIR}/use_external")
  nsx_debug_read_text(PATH "${CMAKE_SOURCE_DIR}/external.txt" OUT NSX_SEGGER_DEVICE)
endif()
file(GLOB members CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/members/*")
add_subdirectory(sub)
nsx_debug_set_primary_target(app)
""",
        encoding="utf-8",
    )
    run(
        cmake,
        "-S",
        source,
        "-B",
        build,
        "-G",
        "Ninja",
        "-DNSX_DEBUG_CONTEXT=ON",
        "-DNSX_DEBUG_INPUT_CONTRACT=1",
    )
    return source, build, helpers


def prepare(
    project: tuple[Path, Path, Path], *, ok: bool = True
) -> subprocess.CompletedProcess[str]:
    _, build, helpers = project
    return run(
        "cmake", f"-DNSX_DEBUG_BUILD_DIR={build}", "-P", helpers / "nsx_debug_prepare.cmake", ok=ok
    )


def test_prepare_readonly_and_private_capture(project: tuple[Path, Path, Path]) -> None:
    source, build, _ = project
    prepare(project)
    ctx = load_debug_context(source, build, "fixture")
    target = ctx.target()
    assert target.device == "device-A"
    assert target.elf == build / "sub/renamed.custom"
    assert target.binary == build / "sub/app.bin"
    assert not target.binary.exists()  # reset needs configuration, not firmware
    before = {p: p.stat().st_mtime_ns for p in build.rglob("*") if p.is_file()}
    assert load_debug_context(source, build, "fixture") == ctx
    assert before == {p: p.stat().st_mtime_ns for p in before}
    with capture_debug_context(source, build, "fixture", operation="reset") as snapshot:
        private = snapshot.directory
        assert not (private / "firmware.bin").exists()
    assert not private.exists()
    run("cmake", "--build", build)
    with capture_debug_context(source, build, "fixture", operation="flash") as snapshot:
        private = snapshot.directory
        binary = (private / "firmware.bin").read_bytes()
        recipe = (private / "flash_cmds.jlink").read_text(encoding="utf-8")
        assert f'LoadFile "{private.as_posix()}/firmware.bin", 0x1000' in recipe
        assert "ExitOnError 1" in recipe
        direct = target.flash_recipe.read_text(encoding="utf-8")
        assert direct == recipe.replace(
            (private / "firmware.bin").as_posix(), target.binary.as_posix()
        )
        target.binary.write_bytes(b"changed after capture")
        assert (private / "firmware.bin").read_bytes() == binary
    assert not private.exists()


@pytest.mark.parametrize("mutation", ["board", "cache", "glob", "directory", "external", "recipe"])
def test_stale_inputs(project: tuple[Path, Path, Path], mutation: str) -> None:
    source, build, _ = project
    (source / "use_external").touch()
    prepare(project)
    if mutation == "board":
        path = source / "board.cmake"
        path.write_text('set(NSX_SEGGER_DEVICE "changed")\n', encoding="utf-8")
    elif mutation == "cache":
        with (build / "CMakeCache.txt").open("a", encoding="utf-8") as stream:
            stream.write("\n# changed\n")
    elif mutation == "glob":
        (source / "members/new").touch()
    elif mutation == "directory":
        (source / "members/one").unlink()
        (source / "members/one").mkdir()
    elif mutation == "external":
        (source / "external.txt").write_text("device-B", encoding="utf-8")
    else:
        (build / "sub/jlink/app/flash_cmds.jlink").write_text("Go\n", encoding="utf-8")
    with pytest.raises(NSXConfigError, match="stale"):
        load_debug_context(source, build, "fixture")
    prepare(project)
    assert load_debug_context(source, build, "fixture").target().device == (
        "device-B" if mutation == "external" else "device-A"
    )


def test_firmware_edit_is_not_connection_staleness(project: tuple[Path, Path, Path]) -> None:
    source, build, _ = project
    prepare(project)
    (source / "main.c").write_text("int main(void) {return 1;}\n", encoding="utf-8")
    assert load_debug_context(source, build, "fixture").target().device == "device-A"


@pytest.mark.parametrize("mutation", ["schema", "duplicate", "primary", "escape", "type"])
def test_strict_reader(project: tuple[Path, Path, Path], mutation: str) -> None:
    source, build, _ = project
    prepare(project)
    path = build / "nsx-debug/context.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if mutation == "schema":
        data["schema_version"] = 2
    elif mutation == "duplicate":
        path.write_text(
            raw.replace('"schema_version" : 1', '"schema_version" : 1, "schema_version": 1'),
            encoding="utf-8",
        )
    elif mutation == "primary":
        data["primary_target"] = "absent"
    elif mutation == "escape":
        data["targets"]["app"]["bin"] = str(source / "escape.bin")
    else:
        data["helper_protocol"] = True
    if mutation != "duplicate":
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(NSXConfigError):
        load_debug_context(source, build, "fixture")


def test_identity_and_failure_invalidation(project: tuple[Path, Path, Path]) -> None:
    source, build, _ = project
    prepare(project)
    with pytest.raises(NSXConfigError, match="identity"):
        load_debug_context(source, build, "wrong")
    with (source / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
        stream.write('\nmessage(FATAL_ERROR "intentional failure")\n')
    assert prepare(project, ok=False).returncode
    assert not (build / "nsx-debug/context.json").exists()


@pytest.mark.parametrize("registered", [False, True])
def test_change_after_evaluation_rejected(
    project: tuple[Path, Path, Path], registered: bool
) -> None:
    source, build, helpers = project
    if registered:
        (source / "use_external").touch()
    # Count configure passes; pause the second compared evaluation, after inputs were read.
    with (source / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
        stream.write("""
if(EXISTS "${CMAKE_BINARY_DIR}/count")
  file(READ "${CMAKE_BINARY_DIR}/count" count)
else()
  set(count 0)
endif()
math(EXPR count "${count}+1")
file(WRITE "${CMAKE_BINARY_DIR}/count" "${count}")
if(count EQUAL 3)
  file(WRITE "${CMAKE_BINARY_DIR}/paused" "yes")
  execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep 1)
endif()
""")
    with subprocess.Popen(
        ["cmake", f"-DNSX_DEBUG_BUILD_DIR={build}", "-P", str(helpers / "nsx_debug_prepare.cmake")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        deadline = time.monotonic() + 20
        while (
            not (build / "paused").exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert (build / "paused").exists()
        path = source / ("external.txt" if registered else "board.cmake")
        path.write_text(
            "device-B" if registered else 'set(NSX_SEGGER_DEVICE "device-B")\n', encoding="utf-8"
        )
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode, stdout + stderr
        assert "changed after read" in stderr if registered else "snapshots disagree" in stderr
    assert not (build / "nsx-debug/context.json").exists()
    prepare(project)
    assert load_debug_context(source, build, "fixture").target().device == "device-B"


def test_context_fields_bound_to_evaluated_generation(project: tuple[Path, Path, Path]) -> None:
    source, build, _ = project
    prepare(project)
    path = build / "nsx-debug/context.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["targets"]["app"]["device"] = "different-device"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(NSXConfigError, match="evaluated generation"):
        load_debug_context(source, build, "fixture")


def test_two_builds_and_preference(project: tuple[Path, Path, Path]) -> None:
    source, build, helpers = project
    other = build.parent / "other build"
    run(
        "cmake",
        "-S",
        source,
        "-B",
        other,
        "-G",
        "Ninja",
        "-DNSX_DEBUG_CONTEXT=ON",
        "-DNSX_DEBUG_INPUT_CONTRACT=1",
        "-DNSX_JLINK_SERIAL=12345",
    )
    prepare(project)
    prepare((source, other, helpers))
    first = load_debug_context(source, build, "fixture")
    second = load_debug_context(source, other, "fixture")
    assert first.target().configured_serial is None
    assert second.target().configured_serial == "12345"
    with pytest.raises(NSXConfigError, match="identity"):
        from neuralspotx.operations._debug_context._reader import _parse

        _parse((other / "nsx-debug/context.json").read_bytes(), source, build, "fixture")
    before = (other / "CMakeCache.txt").read_bytes()
    with capture_debug_context(source, other, "fixture", operation="swo") as snapshot:
        assert (snapshot.directory / "reset_cmds.jlink").read_text(encoding="utf-8") == (
            second.target().reset_recipe.read_text(encoding="utf-8")
        )
    assert (other / "CMakeCache.txt").read_bytes() == before


@pytest.mark.parametrize("change", ["missing", "timestamp"])
def test_content_not_timestamp(project: tuple[Path, Path, Path], change: str) -> None:
    import os

    source, build, _ = project
    prepare(project)
    path = source / "board.cmake"
    before = path.stat()
    if change == "missing":
        path.unlink()
    else:
        path.write_text('set(NSX_SEGGER_DEVICE "device-B")\n', encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(NSXConfigError):
        load_debug_context(source, build, "fixture")


@pytest.mark.parametrize(
    "extra",
    [
        "nsx_debug_set_primary_target(absent)",
        'file(GLOB_RECURSE extra CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/members/*")',
    ],
)
def test_unsupported_producers_rejected(project: tuple[Path, Path, Path], extra: str) -> None:
    source, build, _ = project
    with (source / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
        stream.write("\n" + extra + "\n")
    assert prepare(project, ok=False).returncode
    assert not (build / "nsx-debug/context.json").exists()


def test_capture_mutation_fails_and_cleans(
    project: tuple[Path, Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tempfile

    from neuralspotx.operations._debug_context import _reader

    source, build, helpers = project
    # Fault injection into a copied fixture script; production has no test hook.
    capture = helpers / "nsx_debug_capture.cmake"
    script = capture.read_text(encoding="utf-8")
    script = script.replace(
        'file(COPY_FILE "${source}" "${output}")',
        'file(COPY_FILE "${source}" "${output}")\nfile(WRITE "${source}" "changed")',
    )
    capture.write_text(script, encoding="utf-8")
    monkeypatch.setattr(_reader, "_CMAKE", helpers)
    private_root = tmp_path / "private"
    private_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(private_root))
    prepare(project)
    run("cmake", "--build", build)
    with pytest.raises(NSXConfigError, match="artifact changed"):
        with capture_debug_context(source, build, "fixture", operation="flash"):
            pytest.fail("capture must fail before execution")
    assert not list(private_root.iterdir())


def test_opt_out_retains_direct_targets(project: tuple[Path, Path, Path]) -> None:
    source, build, _ = project
    prepare(project)
    run("cmake", "-S", source, "-B", build, "-DNSX_DEBUG_CONTEXT=OFF")
    assert not (build / "nsx-debug/context.json").exists()
    run("cmake", "--build", build)
    recipe = (build / "sub/jlink/app/flash_cmds.jlink").read_text(encoding="utf-8")
    assert f'LoadFile "{build.as_posix()}/sub/app.bin", 0x1000' in recipe
    assert Path((build / "nsx-artifacts/app.path").read_text(encoding="utf-8").strip()) == (
        build / "sub/renamed.custom"
    )


def test_opt_out_recipe_template_regenerates(project: tuple[Path, Path, Path]) -> None:
    source, build, helpers = project
    run("cmake", "-S", source, "-B", build, "-DNSX_DEBUG_CONTEXT=OFF")
    run("cmake", "--build", build)
    for kind in ("flash", "reset"):
        template = helpers / f"segger/templates/{kind}_cmds.jlink.in"
        with template.open("a", encoding="utf-8") as stream:
            stream.write("// changed template dependency\n")
        run("cmake", "--build", build)
        assert "changed template dependency" in (
            build / f"sub/jlink/app/{kind}_cmds.jlink"
        ).read_text(encoding="utf-8")


def test_attach_capabilities_do_not_require_trace_or_load_address(
    project: tuple[Path, Path, Path],
) -> None:
    source, build, _ = project
    app = source / "CMakeLists.txt"
    text = app.read_text(encoding="utf-8")
    for line in (
        "set(NSX_SEGGER_PF_ADDR 0x1000)",
        "set(NSX_SEGGER_CPUFREQ 96000000)",
        "set(NSX_SEGGER_SWOFREQ 1000000)",
    ):
        text = text.replace(line, "")
    app.write_text(text, encoding="utf-8")
    prepare(project)
    target = load_debug_context(source, build, "fixture").target()
    assert target.reset_unavailable is None
    assert target.rtt_unavailable is None
    assert target.flash_unavailable
    assert target.swo_unavailable
    assert target.cpu_hz is None and target.load_address is None
    with capture_debug_context(source, build, "fixture", operation="reset"):
        pass
    with pytest.raises(NSXConfigError, match="unavailable"):
        with capture_debug_context(source, build, "fixture", operation="swo"):
            pytest.fail("SWO must not capture without trace settings")


def test_capture_refuses_unexported_template_settings(project: tuple[Path, Path, Path]) -> None:
    source, build, helpers = project
    app = source / "CMakeLists.txt"
    app.write_text(
        app.read_text(encoding="utf-8").replace(
            "add_subdirectory(sub)", "set(PRIVATE_TEMPLATE_SETTING value)\nadd_subdirectory(sub)"
        ),
        encoding="utf-8",
    )
    with (helpers / "segger/templates/flash_cmds.jlink.in").open("a", encoding="utf-8") as stream:
        stream.write("// @PRIVATE_TEMPLATE_SETTING@\n")
    prepare(project)
    run("cmake", "--build", build)
    with pytest.raises(NSXConfigError, match="flash template requires settings"):
        with capture_debug_context(source, build, "fixture", operation="flash"):
            pytest.fail("must not silently render a different recipe")
