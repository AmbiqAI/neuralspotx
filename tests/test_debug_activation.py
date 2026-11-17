"""Real CMake context plus fake hardware boundaries: exercise policy, not a mirror exporter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from debug_fixtures import cmake, make_debug_app, prepare

from neuralspotx import AppRttRequest, NSXConfigError, NSXError, api, tooling
from neuralspotx._probe_selection import ProbeSelection
from neuralspotx.models import FlashResult, ResetResult, RttResult
from neuralspotx.operations import _build, _hardware, _rtt
from neuralspotx.operations._debug_workflow import DebugState, inspect_build
from neuralspotx.tooling import JLinkProbe, _JLinkInventoryEntry


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app, build = make_debug_app(tmp_path / "app")
    calls: list[dict] = []
    monkeypatch.setattr(_build, "validate_app_requirements", lambda *a: None)
    monkeypatch.setattr(_build, "regenerate_active_board_glue", lambda *a, **k: None)
    monkeypatch.setattr(_build, "_ensure_app_modules", lambda *a, **k: calls.append({"sync": k}))
    monkeypatch.setattr(_build, "warn_if_lock_stale", lambda *a: None)

    def configure(source, output, board, *, probe_serial=None, **kwargs):
        calls.append({"configure": probe_serial})
        cmake(
            "-S",
            source,
            "-B",
            output,
            f"-DNSX_BOARD={board}",
            f"-DNSX_JLINK_SERIAL={probe_serial or ''}",
        )

    monkeypatch.setattr(_build, "_run_cmake_configure", configure)
    monkeypatch.setattr(_hardware, "find_segger_tool", lambda _: "fake-commander")
    monkeypatch.setattr(_build, "find_segger_tool", lambda _: "fake-viewer")

    real_capture = _build.run_capture

    def execute(cmd, **kwargs):
        if cmd[0] == "cmake":
            return real_capture(cmd, **kwargs)
        assert cmd[0] == "fake-commander"
        serial = cmd[cmd.index("-USB") + 1]
        recipe = Path(cmd[cmd.index("-commandfile") + 1])
        calls.append({
            "serial": serial,
            "recipe": recipe,
            "text": recipe.read_text(encoding="utf-8"),
        })
        return subprocess.CompletedProcess(
            cmd, 0, stdout="Flash download: Total time 0.1s", stderr=""
        )

    monkeypatch.setattr(_build, "run_capture", execute)
    monkeypatch.setattr(_hardware, "run_capture", execute)

    def viewer(source, output, board, name, view_cmd, reset_cmd, **kwargs):
        serial = view_cmd[view_cmd.index("-USB") + 1]
        assert reset_cmd[reset_cmd.index("-USB") + 1] == serial
        recipe = Path(reset_cmd[reset_cmd.index("-commandfile") + 1])
        assert recipe.is_file()
        calls.append({
            "serial": serial,
            "recipe": recipe,
            "text": recipe.read_text(encoding="utf-8"),
        })
        return output

    monkeypatch.setattr(_build, "_run_viewer", viewer)
    monkeypatch.setattr(
        tooling,
        "_list_jlink_inventory",
        lambda: [_JLinkInventoryEntry(JLinkProbe(0, "9999", "fake"), "USB")],
    )
    return app, build, calls


@pytest.mark.parametrize("operation", ["flash", "view", "reset"])
@pytest.mark.parametrize(
    "serial,discover,expected",
    [(None, False, "1234"), ("0005678", False, "0005678"), (None, True, "9999")],
)
def test_selected_once_without_persisting(app, operation, serial, discover, expected):
    root, build, calls = app
    before = (build / "CMakeCache.txt").read_bytes()
    result = {"flash": api.flash_app, "view": api.view_app, "reset": api.reset_target}[operation](
        app_dir=root, probe_serial=serial, discover_probe=discover
    )
    assert [c["serial"] for c in calls if "serial" in c] == [expected]
    assert not any("configure" in c for c in calls)
    assert (build / "CMakeCache.txt").read_bytes() == before
    assert not calls[-1]["recipe"].exists()
    if operation != "view":
        assert isinstance(result, (FlashResult, ResetResult))
        assert result.probe_serial == expected
    if operation == "flash":
        assert isinstance(result, FlashResult)
        assert result.artifact == build / "firmware output/demo.bin"
        assert result.recipe.is_file()
        assert str(result.artifact) not in calls[-1]["text"]


@pytest.mark.parametrize("operation", ["flash", "view", "reset"])
@pytest.mark.parametrize("problem", ["malformed", "wrong_board", "unknown_schema", "cache_owner"])
def test_invalid_state_precedes_any_write_or_hardware(app, monkeypatch, operation, problem):
    root, build, calls = app
    context = build / "nsx-debug/context.json"
    data = json.loads(context.read_text())
    if problem == "malformed":
        context.write_text("{")
    elif problem == "cache_owner":
        cache = build / "CMakeCache.txt"
        cache.write_text(
            cache.read_text().replace(root.as_posix(), (root.parent / "other").as_posix())
        )
    else:
        data["board" if problem == "wrong_board" else "schema_version"] = (
            "other" if problem == "wrong_board" else 999
        )
        context.write_text(json.dumps(data))
    monkeypatch.setattr(
        _build, "regenerate_active_board_glue", lambda *a, **k: pytest.fail("write")
    )
    with pytest.raises(NSXConfigError):
        {"flash": api.flash_app, "view": api.view_app, "reset": api.reset_target}[operation](
            app_dir=root, probe_serial="88"
        )
    assert calls == []


def test_stale_reprepare_preserves_preference_but_attach_refuses(app):
    root, build, calls = app
    with (root / "board.cmake").open("a") as f:
        f.write("\n# changed input\n")
    assert inspect_build(root, build, "apollo510_evb").state is DebugState.STALE
    with pytest.raises(NSXConfigError):
        api.reset_target(app_dir=root, probe_serial="88")
    assert calls == []
    result = api.flash_app(root, probe_serial="88")
    assert result.probe_serial == "88"
    assert inspect_build(root, build, "apollo510_evb").preference == "1234"


def test_configure_clear_and_implicit_preserve(app):
    root, build, calls = app
    api.configure_app(root, probe_serial="00123")
    assert inspect_build(root, build, "apollo510_evb").preference == "00123"
    (build / "build.ninja").unlink()
    api.build_app(root)
    assert calls[-1] == {"configure": "00123"}
    api.configure_app(root)
    assert inspect_build(root, build, "apollo510_evb").preference is None


def test_frozen_gate_before_ninja_or_glue(app, monkeypatch):
    root, _, calls = app

    def drift(*a, **k):
        raise NSXConfigError("locked dependency drift")

    monkeypatch.setattr(_build, "_ensure_app_modules", drift)
    monkeypatch.setattr(
        _build,
        "regenerate_active_board_glue",
        lambda *a, **k: pytest.fail("glue before verification"),
    )
    with pytest.raises(NSXConfigError, match="drift"):
        api.flash_app(root, frozen=True)
    assert calls == []


@pytest.mark.parametrize("transports", [[], ["IP"], [None], ["USB", "USB"], ["USB", "USB", "IP"]])
def test_only_unique_local_usb_is_eligible(monkeypatch, transports):
    monkeypatch.setattr(
        tooling,
        "_list_jlink_inventory",
        lambda: [
            _JLinkInventoryEntry(JLinkProbe(i, "123", "same"), t) for i, t in enumerate(transports)
        ],
    )
    with pytest.raises(NSXConfigError, match="eligible local USB"):
        ProbeSelection.from_request(None).resolve()


def test_explicit_selection_does_not_enumerate_or_fallback(monkeypatch):
    monkeypatch.setattr(tooling, "_list_jlink_inventory", lambda: pytest.fail("enumerated"))
    assert ProbeSelection.from_request("0007").resolve() == "0007"
    assert ProbeSelection.from_request(None, configured="0008").resolve() == "0008"


def test_rtt_capture_recomputes_from_private_elf(app, monkeypatch):
    if sys.platform != "linux":
        pytest.skip("ELF host fixture")
    from neuralspotx import _rtt_capture

    root, build, calls = app
    seen = []
    read = _rtt._rtt_address

    def address(path):
        seen.append(path)
        return read(path)

    monkeypatch.setattr(_rtt, "_rtt_address", address)

    def capture(settings, **kwargs):
        assert seen[-1].name == "firmware.elf" and seen[-1].is_file()
        assert settings.elf == build / "firmware output/demo"
        assert settings.probe_serial is None
        return RttResult(settings, 0, None)

    monkeypatch.setattr(_rtt_capture, "capture_rtt", capture)
    api.rtt_app(AppRttRequest(root, discover_probe=True))
    assert not seen[-1].exists()
    assert calls == []


def test_failed_connection_keeps_selected_probe(app, monkeypatch):
    root, _, calls = app

    def failed(*a, **k):
        raise subprocess.CalledProcessError(1, a[0], stderr="unplugged")

    monkeypatch.setattr(_hardware, "run_capture", failed)
    monkeypatch.setattr(
        tooling, "_list_jlink_inventory", lambda: pytest.fail("fallback enumeration")
    )
    with pytest.raises(NSXError, match="unplugged"):
        api.reset_target(app_dir=root, verify_reconnect=True)
    assert calls == []


@pytest.mark.parametrize("operation", ["flash", "view", "reset", "rtt"])
def test_invalid_selection_precedes_any_app_work(tmp_path, monkeypatch, operation):
    from neuralspotx.operations import _reset

    def no_app(*a, **k):
        pytest.fail("app resolution before request validation")

    for mod in (_build, _reset, _rtt):
        monkeypatch.setattr(mod, "_resolve_build_context", no_app)
    with pytest.raises(NSXConfigError, match="either"):
        if operation == "rtt":
            api.rtt_app(AppRttRequest(tmp_path, probe_serial="123", discover_probe=True))
        else:
            {"flash": api.flash_app, "view": api.view_app, "reset": api.reset_target}[operation](
                app_dir=tmp_path, probe_serial="123", discover_probe=True
            )


def test_disabled_or_unknown_protocol_never_falls_back(app):
    root, build, calls = app
    cmake("-S", root, "-B", build, "-DNSX_DEBUG_CONTEXT=OFF")
    with pytest.raises(NSXConfigError, match="adoption"):
        api.flash_app(root, probe_serial="88")
    (build / "nsx-debug/protocol").write_text("99\n", encoding="utf-8")
    with pytest.raises(NSXConfigError, match="protocol"):
        api.reset_target(app_dir=root, probe_serial="88")
    assert calls == []


def test_discovery_failure_is_not_zero_inventory(monkeypatch):
    from neuralspotx._errors import NSXToolchainError

    def failed():
        raise NSXToolchainError("discovery launch failed")

    monkeypatch.setattr(tooling, "_list_jlink_inventory", failed)
    with pytest.raises(NSXToolchainError, match="launch failed"):
        ProbeSelection.from_request(None).resolve()


def test_reconnect_uses_same_serial(app):
    root, _, calls = app
    api.reset_target(app_dir=root, discover_probe=True, verify_reconnect=True)
    assert [c["serial"] for c in calls] == ["9999", "9999"]


def test_preparation_obeys_subprocess_budget(app):
    from neuralspotx.operations._debug_workflow import prepare_debug
    from neuralspotx.subprocess_utils import timeout_budget

    root, build, _ = app
    (build / "nsx-debug/context.json").unlink()
    script = root / "cmake/nsx/nsx_debug_prepare.cmake"
    script.write_text(
        f'execute_process(COMMAND "{Path(sys.executable).as_posix()}" -c "import time; time.sleep(30)")\n',
        encoding="utf-8",
    )
    with pytest.raises(NSXError, match="timed out"), timeout_budget(0.2):
        prepare_debug(root, build, "apollo510_evb", required=True)
    assert not (build / "nsx-debug/context.json").exists()


@pytest.mark.parametrize("operation", ["flash", "build"])
def test_update_validates_context_before_mutating(app, monkeypatch, operation):
    from neuralspotx import cli

    root, build, _ = app
    (build / "nsx-debug/context.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(api, "update_app", lambda *a, **k: pytest.fail("updated invalid app"))
    assert cli.main([operation, str(root), "--update"]) == 1


def test_template_default_follows_board_without_overriding_author(tmp_path):
    from debug_fixtures import ROOT

    project = tmp_path / "CMakeLists.txt"
    project.write_text(
        "cmake_minimum_required(VERSION 3.31)\nproject(defaults NONE)\n"
        "set(CMAKE_C_COMPILER_ID GNU)\nset(CMAKE_SYSTEM_PROCESSOR arm)\n"
        f'include("{(ROOT / "nsx_debug_template.cmake").as_posix()}")\n',
        encoding="utf-8",
    )
    build = tmp_path / "build"
    from neuralspotx.operations._cmake_cache import _cmake_cache_value

    cmake("-S", tmp_path, "-B", build, "-G", "Ninja", "-DNSX_BOARD=apollo510_evb")
    assert _cmake_cache_value(build, "NSX_DEBUG_CONTEXT") == "ON"
    cmake("-S", tmp_path, "-B", build, "-DNSX_BOARD=apollo4p_evb")
    assert _cmake_cache_value(build, "NSX_DEBUG_CONTEXT") == "OFF"
    cmake("-S", tmp_path, "-B", build, "-G", "Ninja", "-DNSX_BOARD=apollo510_evb")
    assert _cmake_cache_value(build, "NSX_DEBUG_CONTEXT") == "ON"
    cmake("-S", tmp_path, "-B", build, "-DNSX_DEBUG_CONTEXT=OFF")
    cmake("-S", tmp_path, "-B", build)
    assert _cmake_cache_value(build, "NSX_DEBUG_CONTEXT") == "OFF"
    cmake(
        "-S",
        tmp_path,
        "-B",
        build,
        "-DNSX_BOARD=apollo4p_evb",
        "-DNSX_DEBUG_CONTEXT=ON",
        "-DNSX_DEBUG_INPUT_CONTRACT=1",
    )
    assert _cmake_cache_value(build, "NSX_DEBUG_CONTEXT") == "ON"


def test_named_target_and_repaired_recipe_use_actual_producer(app):
    root, build, calls = app
    with (root / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
        stream.write("""
add_executable(secondary main.c)
set_target_properties(secondary PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/second output")
add_custom_command(TARGET secondary POST_BUILD COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:secondary> $<TARGET_FILE_DIR:secondary>/secondary.bin)
nsx_add_segger_targets(secondary)
""")
    prepare(root, build)
    result = api.flash_app(root, target="secondary", probe_serial="42")
    assert result.artifact == build / "second output/secondary.bin"
    assert result.recipe == build / "jlink/secondary/flash_cmds.jlink"
    assert calls[-1]["serial"] == "42"
    # Changed recipe is stale and repaired from CMake before hardware execution.
    result.recipe.write_text('LoadFile "other.bin", 0x0\n', encoding="utf-8")
    api.flash_app(root, target="secondary", probe_serial="42")
    assert "other.bin" not in calls[-1]["text"]
    assert "0x1000" in calls[-1]["text"]


def test_failed_board_replacement_requires_explicit_repair(tmp_path):
    root, build = make_debug_app(tmp_path / "app", board="apollo4p_evb")
    source = root / "CMakeLists.txt"
    original = source.read_text()
    source.write_text(
        original.replace("include(board.cmake)", 'message(FATAL_ERROR "interrupted board switch")')
    )
    failed = subprocess.run(
        ["cmake", "-S", str(root), "-B", str(build), "-DNSX_BOARD=apollo510_evb"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert failed.returncode != 0
    assert "interrupted board switch" in failed.stderr
    source.write_text(original)
    before = (build / "CMakeCache.txt").read_bytes()
    with pytest.raises(NSXConfigError, match="Incomplete CMake board replacement"):
        inspect_build(root, build, "apollo510_evb")
    assert (build / "CMakeCache.txt").read_bytes() == before
    assert (
        inspect_build(root, build, "apollo510_evb", replace_board=True).state
        is DebugState.UNPREPARED
    )
    # Explicit configure owns replacement and clears the old preference by default.
    cmake("-S", root, "-B", build, "-DNSX_BOARD=apollo510_evb", "-DNSX_JLINK_SERIAL=")
    prepare(root, build)
    assert inspect_build(root, build, "apollo510_evb").preference is None


@pytest.mark.parametrize("operation", ["build", "flash"])
def test_update_validates_sdk_override_before_mutating(app, monkeypatch, operation):
    from neuralspotx import cli

    root, _, _ = app
    monkeypatch.setattr(api, "update_app", lambda *a, **k: pytest.fail("updated invalid request"))
    assert (
        cli.main([operation, str(root), "--update", "--sdk-root", str(root / "missing-sdk")]) == 1
    )


def test_swo_preserves_app_target_when_reset_primary_differs(app):
    root, build, calls = app
    source = root / "CMakeLists.txt"
    source.write_text(
        source.read_text().replace("nsx_debug_set_primary_target(demo)", "")
        + """
set(NSX_JLINK_SERIAL 5678)
add_executable(reset_primary main.c)
add_custom_command(TARGET reset_primary POST_BUILD COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:reset_primary> $<TARGET_FILE_DIR:reset_primary>/reset_primary.bin)
nsx_add_segger_targets(reset_primary)
nsx_debug_set_primary_target(reset_primary)
"""
    )
    prepare(root, build)
    cmake("--build", build)
    api.view_app(root)
    assert calls[-1]["serial"] == "1234"
    assert "reset_primary" not in calls[-1]["text"]


@pytest.mark.parametrize("failing_build", [1, 2])
def test_flash_build_failure_is_public_error_before_hardware(app, monkeypatch, failing_build):
    root, _, calls = app
    count = 0

    def fail_build(command, **kwargs):
        nonlocal count
        count += 1
        if count == failing_build:
            raise subprocess.CalledProcessError(1, command, stderr="compiler failed")

    monkeypatch.setattr(_build, "_run_build", fail_build)
    with pytest.raises(NSXError, match="Flash build for target 'demo'"):
        api.flash_app(root)
    assert count == failing_build
    assert not any("serial" in call for call in calls)


@pytest.mark.parametrize("generator,version", [("Unix Makefiles", "3.31"), ("Ninja", "3.30")])
def test_template_auto_adoption_requires_supported_cmake(tmp_path, generator, version):
    from debug_fixtures import ROOT

    script = tmp_path / "defaults.cmake"
    script.write_text(
        "set(NSX_BOARD apollo510_evb)\nset(CMAKE_C_COMPILER_ID GNU)\n"
        "set(CMAKE_SYSTEM_PROCESSOR arm)\n"
        f'set(CMAKE_GENERATOR "{generator}")\nset(CMAKE_VERSION {version})\n'
        f'include("{(ROOT / "nsx_debug_template.cmake").as_posix()}")\n'
        'if(NSX_DEBUG_CONTEXT)\nmessage(FATAL_ERROR "unsupported auto adoption")\nendif()\n'
    )
    cmake("-P", script)


def test_flash_build_output_uses_emitter(app, monkeypatch, capsys):
    root, _, _ = app
    execute = _build.run_capture
    builds = []

    def capture(command, **kwargs):
        if command[0] == "cmake":
            builds.append(command)
            return subprocess.CompletedProcess(
                command, 0, stdout="compiler output", stderr="compiler warning"
            )
        return execute(command, **kwargs)

    monkeypatch.setattr(_build, "run_capture", capture)
    capsys.readouterr()
    events = []
    api.flash_app(root, emit=events.append)
    output = capsys.readouterr()
    assert not output.out and not output.err
    assert len(builds) == 2
    assert sum(event.message == "compiler output" for event in events) == 2
    assert sum(event.message == "compiler warning" for event in events) == 2


@pytest.mark.parametrize("explicit", [False, True])
def test_failed_board_switch_with_retained_context_has_actionable_remedy(tmp_path, explicit):
    root, build = make_debug_app(tmp_path / "app", board="apollo4p_evb")
    source = root / "CMakeLists.txt"
    original = source.read_text()
    source.write_text(
        original.replace(
            "include(cmake/nsx/nsx_helpers.cmake)", 'message(FATAL_ERROR "before helper loading")'
        )
    )
    failed = subprocess.run(
        ["cmake", "-S", str(root), "-B", str(build), "-DNSX_BOARD=apollo510_evb"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert failed.returncode != 0 and "before helper loading" in failed.stderr
    assert (build / "nsx-debug/context.json").is_file()
    source.write_text(original)
    with pytest.raises(NSXConfigError, match="fresh --build-dir"):
        inspect_build(root, build, "apollo510_evb", replace_board=explicit)
