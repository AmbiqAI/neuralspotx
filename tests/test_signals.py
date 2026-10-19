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


@posix_only
def test_inherited_ignore_is_kept_so_nohup_still_works() -> None:
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        with terminate_on_signals():
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.2)
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGHUP, previous)


@posix_only
def test_second_signal_during_cleanup_is_ignored() -> None:
    cleaned = False
    with pytest.raises(TerminatedBySignal), terminate_on_signals():
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)
        finally:
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(0.2)
            cleaned = True
    assert cleaned


def test_cli_exits_130_on_ctrl_c_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _interrupted(_args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_doctor", _interrupted)

    assert cli.main(["doctor"]) == 130
    assert "interrupted by Ctrl-C" in capsys.readouterr().err


@posix_only
def test_terminate_live_children_stops_a_worker_threads_child() -> None:
    import threading

    from neuralspotx.subprocess_utils import _runner, run, terminate_live_children

    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            run([sys.executable, "-c", "import time; time.sleep(60)"])
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=_worker)
    thread.start()
    deadline = time.monotonic() + 15
    while not _runner._LIVE:
        assert time.monotonic() < deadline, "child never registered"
        time.sleep(0.05)

    terminate_live_children()
    thread.join(timeout=15)

    assert not thread.is_alive()
    assert errors and isinstance(errors[0], subprocess.CalledProcessError)
    assert not _runner._LIVE


def test_parallel_map_does_not_wait_for_running_workers_after_a_failure() -> None:
    from neuralspotx._parallel import parallel_map

    def _work(item: int) -> int:
        if item == 0:
            raise RuntimeError("first item failed")
        time.sleep(3)
        return item

    started = time.monotonic()
    with pytest.raises(RuntimeError):
        parallel_map(_work, [0, 1, 2], max_workers=3)
    assert time.monotonic() - started < 2


def test_attach_does_not_raise_when_the_job_object_cannot_be_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Popen stand-in without a Win32 handle must not break the caller (Windows path)."""

    import types

    from neuralspotx.subprocess_utils import _winjob

    # Drive the real Windows branch on any host: a job is created, then
    # reading the stand-in's Win32 handle raises AttributeError.
    closed: list[int] = []
    monkeypatch.setattr(_winjob, "os", types.SimpleNamespace(name="nt"))
    monkeypatch.setattr(_winjob, "_create_kill_on_close_job", lambda: 7)
    monkeypatch.setattr(_winjob, "_assign_process_to_job", lambda job, handle: None)
    monkeypatch.setattr(_winjob, "_close_handle", closed.append)
    container = _winjob._ProcessContainer()

    class _NoHandle:
        pid = 1

    container.attach(_NoHandle())  # ty: ignore[invalid-argument-type]  # deliberate stand-in without _handle
    assert closed == [7]


def test_no_child_starts_once_nsx_is_shutting_down() -> None:
    from neuralspotx.subprocess_utils import run, run_capture, terminate_live_children
    from neuralspotx.subprocess_utils._runner import ChildStartRefused

    terminate_live_children()

    with pytest.raises(ChildStartRefused):
        run([sys.executable, "-c", "pass"])
    with pytest.raises(ChildStartRefused):
        run_capture([sys.executable, "-c", "pass"])


def test_git_retry_stops_once_nsx_is_shutting_down(
    fresh_shutdown_flag: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from neuralspotx.subprocess_utils import _git

    assert isinstance(fresh_shutdown_flag, threading.Event)
    slept: list[float] = []
    monkeypatch.setattr(_git, "_sleep", slept.append)
    calls = 0

    def _killed_git() -> None:
        nonlocal calls
        calls += 1
        # A git child stopped by the cleanup: non-zero exit, no output,
        # which the retry logic would otherwise treat as transient.
        fresh_shutdown_flag.set()
        raise subprocess.CalledProcessError(-15, ["git", "fetch"], output="", stderr="")

    with pytest.raises(subprocess.CalledProcessError):
        _git._git_network_retry(_killed_git, label="git fetch")

    assert calls == 1
    assert slept == []
