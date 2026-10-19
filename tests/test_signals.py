"""SIGTERM/SIGHUP take nsx's children down with it (#293)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from neuralspotx import cli
from neuralspotx.subprocess_utils import (
    TerminatedBySignal,
    die_with_parent_preexec,
    terminate_on_signals,
)

posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX signals")


@posix_only
@pytest.mark.parametrize("name", ["SIGTERM", "SIGHUP"])
def test_termination_signal_raises_terminated_by_signal(name: str) -> None:
    signum = getattr(signal, name)
    before = signal.getsignal(signum)

    with pytest.raises(TerminatedBySignal) as excinfo, terminate_on_signals():
        os.kill(os.getpid(), signum)
        time.sleep(5)

    assert excinfo.value.signum == signum
    assert excinfo.value.signal_name == name
    assert excinfo.value.exit_code == 128 + signum
    assert isinstance(excinfo.value, KeyboardInterrupt)
    assert signal.getsignal(signum) == before


@posix_only
def test_cli_exits_with_128_plus_signum_on_sigterm(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _killed(_args: object) -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(5)

    monkeypatch.setattr(cli, "cmd_doctor", _killed)

    assert cli.main(["doctor"]) == 128 + signal.SIGTERM
    assert "interrupted by SIGTERM" in capsys.readouterr().err


def test_die_with_parent_only_on_linux() -> None:
    hook = die_with_parent_preexec()
    assert (hook is not None) == sys.platform.startswith("linux")


_PARENT = textwrap.dedent(
    """
    import sys
    from neuralspotx.subprocess_utils import TerminatedBySignal, run, terminate_on_signals

    child = (
        "import os, sys, time\\n"
        "open(sys.argv[1], 'w').write(str(os.getpid()))\\n"
        "time.sleep(60)\\n"
    )
    try:
        with terminate_on_signals():
            run([sys.executable, "-c", child, sys.argv[1]])
    except TerminatedBySignal as exc:
        sys.exit(exc.exit_code)
    """
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@posix_only
def test_sigterm_to_parent_stops_child_in_its_own_session(tmp_path: Path) -> None:
    """Real processes: the child runs in its own session, like the SWO viewer."""

    pid_file = tmp_path / "child.pid"
    parent = subprocess.Popen([sys.executable, "-c", _PARENT, str(pid_file)])
    try:
        deadline = time.monotonic() + 30
        while not (pid_file.exists() and pid_file.read_text()):
            assert time.monotonic() < deadline, "child never started"
            time.sleep(0.05)
        child_pid = int(pid_file.read_text())

        parent.send_signal(signal.SIGTERM)
        assert parent.wait(timeout=15) == 128 + signal.SIGTERM

        deadline = time.monotonic() + 10
        while _alive(child_pid):
            assert time.monotonic() < deadline, "child outlived its parent"
            time.sleep(0.05)
    finally:
        if parent.poll() is None:
            parent.kill()
        if pid_file.exists() and pid_file.read_text():
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
