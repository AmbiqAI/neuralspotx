"""Tests for J-Link probe enumeration in :mod:`neuralspotx.tooling`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from neuralspotx import tooling
from neuralspotx._errors import NSXToolchainError
from neuralspotx.tooling import JLinkProbe, find_processes_holding_probe, list_jlink_probes

_SAMPLE_EMU_LIST = """\
J-Link[0]: Connection: USB, Serial number: 1160002204, ProductName: J-Link-OB-Apollo4-CortexM
J-Link[1]: Connection: USB, Serial number: 1160001481, ProductName: J-Link-OB-Apollo4-CortexM, Nickname: <Not set>
J-Link[2]: Connection: USB, Serial number: 9000001234, ProductName: J-Link-Pro, Nickname: bench-rig
"""


def _fake_run(stdout: str):
    def _run(*_args, **_kwargs):
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


def test_list_jlink_probes_returns_empty_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="JLinkExe", timeout=15)

    monkeypatch.setattr(tooling, "find_segger_tool", lambda _names: "/usr/bin/JLinkExe")
    monkeypatch.setattr(tooling.subprocess, "run", _raise)

    assert list_jlink_probes() == []


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
    monkeypatch.delenv("JLINK_PATH", raising=False)
    monkeypatch.setattr(tooling, "tool_path", lambda _name: None)
    monkeypatch.setattr(tooling.Path, "is_file", lambda path: str(path) == candidate)
    assert tooling.find_segger_tool(tooling.JLINK_NAMES) == candidate


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
