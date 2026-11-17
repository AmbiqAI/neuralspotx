"""Tests for J-Link probe enumeration in :mod:`neuralspotx.tooling`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from neuralspotx import tooling
from neuralspotx._errors import NSXTimeoutError, NSXToolchainError
from neuralspotx.tooling import JLinkProbe, find_processes_holding_probe, list_jlink_probes

_SAMPLE_EMU_LIST = """\
J-Link[0]: Connection: USB, Serial number: 1160002204, ProductName: J-Link-OB-Apollo4-CortexM
J-Link[1]: Connection: USB, Serial number: 1160001481, ProductName: J-Link-OB-Apollo4-CortexM, Nickname: <Not set>
J-Link[2]: Connection: USB, Serial number: 9000001234, ProductName: J-Link-Pro, Nickname: bench-rig
"""


def _fake_run(response: str):
    def _run(*_args, **_kwargs):
        script = Path(_args[0][-1])
        assert script.read_text(encoding="ascii") == "ShowEmuList\nexit\n"
        assert _args[0][1:-2] == ["-nogui", "1", "-AutoConnect", "0"]
        stdout = (
            "SEGGER J-Link Commander V9.50\n"
            "J-Link>ShowEmuList\n" + response + "\nJ-Link>exit\n"
            "Script processing completed.\n"
        )
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    return _run


def test_list_jlink_probes_parses_emu_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _names: "/usr/bin/JLinkExe")
    monkeypatch.setattr(tooling.subprocess, "run", _fake_run(_SAMPLE_EMU_LIST))

    probes = list_jlink_probes()

    assert probes == [
        JLinkProbe(
            index=0, serial="1160002204", product="J-Link-OB-Apollo4-CortexM", nickname=None
        ),
        JLinkProbe(
            index=1, serial="1160001481", product="J-Link-OB-Apollo4-CortexM", nickname=None
        ),
        JLinkProbe(index=2, serial="9000001234", product="J-Link-Pro", nickname="bench-rig"),
    ]


def test_list_jlink_probes_empty_when_no_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _names: "/usr/bin/JLinkExe")
    monkeypatch.setattr(tooling.subprocess, "run", _fake_run("No emulators connected.\n"))

    assert list_jlink_probes() == []


@pytest.mark.parametrize("ambient,expected", [(None, 15), (0.0, 0.0), (0.2, 0.2), (30, 15)])
def test_list_jlink_probes_reports_timeout(monkeypatch, ambient, expected):
    from neuralspotx.subprocess_utils import _effective_timeout, timeout_budget

    scripts = []

    def expire(command, **kwargs):
        scripts.append(Path(command[-1]))
        assert scripts[-1].is_file()
        assert kwargs["timeout"] == expected
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "fake-commander")
    monkeypatch.setattr(tooling.subprocess, "run", expire)
    with timeout_budget(ambient):
        with pytest.raises(NSXTimeoutError) as caught:
            list_jlink_probes()
        assert _effective_timeout(None) == ambient
    assert caught.value.timeout_s == expected
    assert caught.value.command and "fake-commander" in caught.value.command
    assert len(scripts) == 1 and not scripts[0].exists()


def test_list_jlink_probes_raises_without_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _names: None)

    with pytest.raises(NSXToolchainError):
        list_jlink_probes()


def test_find_jlink_honors_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commander = tmp_path / "SEGGER tools" / "JLink.exe"
    commander.parent.mkdir()
    commander.write_bytes(b"")
    monkeypatch.setenv("JLINK_PATH", str(commander))
    assert tooling.find_segger_tool(tooling.JLINK_NAMES) == str(commander)


@pytest.mark.parametrize(
    "candidate",
    ["/usr/local/bin/JLinkExe", "/Applications/SEGGER/JLink/JLinkExe"],
)
def test_find_jlink_checks_posix_install_locations(
    candidate: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = Path(candidate)
    monkeypatch.delenv("JLINK_PATH", raising=False)
    monkeypatch.setattr(tooling, "tool_path", lambda _name: None)
    monkeypatch.setattr(tooling.Path, "is_file", lambda path: path == expected)
    assert tooling.find_segger_tool(tooling.JLINK_NAMES) == str(expected)


def test_find_jlink_checks_windows_install_location(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = Path("C:/Program Files/SEGGER/JLink/JLink.exe")
    monkeypatch.delenv("JLINK_PATH", raising=False)
    monkeypatch.setenv("ProgramFiles", "C:/Program Files")
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.setattr(tooling, "tool_path", lambda _name: None)
    monkeypatch.setattr(tooling.Path, "is_file", lambda path: path == expected)
    assert tooling.find_segger_tool(tooling.JLINK_NAMES) == str(expected)


def test_find_processes_holding_probe_matches_segger_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = [
        (4242, "JLinkSWOViewer_CL -USB 1160001350 -device AMA4B2KP-KXR -itmport 0"),
        (4243, "/usr/bin/python3 some_script.py 1160001350"),  # serial but not SEGGER
        (4244, "JLinkExe -USB 9999999999 -nogui 1"),  # SEGGER but other serial
    ]
    monkeypatch.setattr(tooling, "_iter_process_cmdlines", lambda: iter(fake))

    assert find_processes_holding_probe("1160001350") == [4242]


def test_find_processes_holding_probe_excludes_self(monkeypatch: pytest.MonkeyPatch) -> None:
    me = tooling.os.getpid()
    fake = [(me, "JLinkSWOViewer_CL -USB 1160001350 -itmport 0")]
    monkeypatch.setattr(tooling, "_iter_process_cmdlines", lambda: iter(fake))

    assert find_processes_holding_probe("1160001350") == []


def test_find_processes_holding_probe_empty_serial() -> None:
    assert find_processes_holding_probe("") == []


@pytest.mark.parametrize("name,count", [("empty", 0), ("populated", 5)])
def test_recorded_commander_inventory(
    monkeypatch: pytest.MonkeyPatch, name: str, count: int
) -> None:
    output = (Path(__file__).parent / "fixtures/jlink" / f"showemulist-{name}.txt").read_text()
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")
    monkeypatch.setattr(
        tooling.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, output, "")
    )
    assert len(list_jlink_probes()) == count


@pytest.mark.parametrize(
    "response",
    [
        "ERROR: Could not enumerate probes.",
        "J-Link[0]: Connection: USB, Serial number: 1234",
        "No emulators connected.\n" + _SAMPLE_EMU_LIST,
        _SAMPLE_EMU_LIST + "J-Link[3]: broken row",
    ],
)
def test_failed_or_partial_inventory_is_not_success(
    monkeypatch: pytest.MonkeyPatch, response: str
) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")
    monkeypatch.setattr(tooling.subprocess, "run", _fake_run(response))
    with pytest.raises(NSXToolchainError, match="discovery failed"):
        list_jlink_probes()


@pytest.mark.parametrize(
    "output", ["", "Command not recognized", "J-Link>ShowEmuList\nJ-Link>exit\n", _SAMPLE_EMU_LIST]
)
def test_incomplete_script_is_not_empty_inventory(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")
    monkeypatch.setattr(
        tooling.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, output, "")
    )
    with pytest.raises(NSXToolchainError, match="discovery failed"):
        list_jlink_probes()


def test_launch_failure_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")

    def fail(*args, **kwargs):
        raise PermissionError("not executable")

    monkeypatch.setattr(tooling.subprocess, "run", fail)
    with pytest.raises(NSXToolchainError, match="could not run Commander.*not executable"):
        list_jlink_probes()


def test_nonzero_exit_rejects_even_valid_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")
    monkeypatch.setattr(
        tooling.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 1, _SAMPLE_EMU_LIST, "USB failure"),
    )
    with pytest.raises(NSXToolchainError, match="status 1: USB failure"):
        list_jlink_probes()


def test_nickname_error_word_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")
    monkeypatch.setattr(
        tooling.subprocess, "run", _fake_run(_SAMPLE_EMU_LIST.replace("bench-rig", "error-test"))
    )
    assert list_jlink_probes()[-1].nickname == "error-test"


def test_transport_is_parsed_from_prefix_not_nickname(monkeypatch: pytest.MonkeyPatch) -> None:
    from neuralspotx._probe_selection import ProbeSelection

    inventory = (
        "J-Link[0]: Serial number: 1, ProductName: unknown, Nickname: Connection: USB,\n"
        "J-Link[1]: Connection: IP, Serial number: 2, ProductName: remote\n"
        "J-Link[2]: Connection: USB, Serial number: 003, ProductName: local\n"
    )
    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "fake")
    monkeypatch.setattr(tooling.subprocess, "run", _fake_run(inventory))
    assert len(tooling.list_jlink_probes()) == 3
    assert ProbeSelection.from_request(None).resolve() == "003"
