"""Helpers for subprocess execution and tool-specific error formatting.

All long-running shell-outs (``cmake``, ``ninja``, ``git``, ``JLinkExe``)
go through :func:`run` and :func:`run_capture` here so that callers get
two guarantees out of the box:

* **Process-tree kill** — children are spawned in their own process group
  (``start_new_session=True``); on timeout we SIGTERM, then SIGKILL the
  whole group, so a hung ``cmake`` cannot leave ``ninja`` and the
  compiler running in the background.
* **Caller-scoped timeout** — wrapping a region with
  :func:`timeout_budget` sets a default wall-clock budget for every
  subprocess inside it without having to thread a ``timeout=`` argument
  through every helper.  An explicit ``timeout=`` kwarg always wins.
"""

from __future__ import annotations

import contextlib
import contextvars
import ctypes
import os
import select
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

from ._errors import NSXTimeoutError

# Verbosity for subprocess error formatting.  Stored in a ContextVar so
# concurrent callers (threads, asyncio tasks, embedders) can scope their
# own level without racing on a module-level global.
_VERBOSITY: contextvars.ContextVar[int] = contextvars.ContextVar(
    "nsx_subprocess_verbosity", default=0
)

# Default wall-clock budget for each subprocess inside a region wrapped
# by :func:`timeout_budget`.  ``None`` means "no implicit timeout";
# explicit ``timeout=`` kwargs on individual calls still apply.
_TIMEOUT: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "nsx_subprocess_timeout", default=None
)


def set_verbosity(level: int) -> None:
    """Set subprocess helper verbosity in the current context."""

    _VERBOSITY.set(level)


def get_verbosity() -> int:
    """Return the verbosity level visible to the current context."""

    return _VERBOSITY.get()


@contextlib.contextmanager
def verbosity(level: int) -> Iterator[None]:
    """Temporarily override subprocess verbosity for a scope."""

    token = _VERBOSITY.set(level)
    try:
        yield
    finally:
        _VERBOSITY.reset(token)


@contextlib.contextmanager
def timeout_budget(seconds: float | None) -> Iterator[None]:
    """Set a default per-subprocess wall-clock timeout for this scope.

    Calls to :func:`run` / :func:`run_capture` inside the ``with`` block
    use *seconds* as their default timeout.  ``None`` clears any
    inherited budget.

    Any :class:`subprocess.TimeoutExpired` raised inside the block is
    translated into :class:`NSXTimeoutError` so callers can rely on the
    typed exception hierarchy.
    """
    token = _TIMEOUT.set(seconds)
    try:
        yield
    except subprocess.TimeoutExpired as exc:
        cmd = exc.cmd
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        raise NSXTimeoutError(
            f"Subprocess timed out after {exc.timeout}s: {cmd_str}",
            command=cmd_str,
            timeout_s=float(exc.timeout) if exc.timeout is not None else None,
        ) from None
    finally:
        _TIMEOUT.reset(token)


def _effective_timeout(explicit: float | None) -> float | None:
    return explicit if explicit is not None else _TIMEOUT.get()


# ---------------------------------------------------------------------------
# Windows process-tree containment via Job Objects
#
# POSIX gets process-tree termination "for free" via ``start_new_session=True``
# + ``killpg``: every grandchild inherits the new process group, so one
# ``killpg(SIGKILL)`` reaps ``cmake``, ``ninja``, ``cl.exe``, link.exe, etc.
#
# Windows has no such inheritance.  ``proc.kill()`` only terminates the
# direct child, so a hung ``cmake`` would leave ``ninja`` and the compiler
# running in the background — the "ghost ninja" problem.
#
# The Win32 fix is a Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``:
# any process assigned to the job (and every descendant it spawns) is
# guaranteed to die when the job handle is closed or ``TerminateJobObject``
# is called.  We attach the child immediately after ``Popen`` and keep the
# handle alive until ``_close_container`` is called from the wait/teardown
# path.
# ---------------------------------------------------------------------------


class _ProcessContainer:
    """Per-subprocess container that owns the Win32 Job handle (if any).

    On POSIX this is just a sentinel; the heavy lifting is done by
    ``start_new_session=True`` + ``killpg`` on the process group.
    """

    __slots__ = ("_job_handle",)

    def __init__(self) -> None:
        self._job_handle: int | None = None

    def attach(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        if os.name != "nt":
            return
        try:
            self._job_handle = _create_kill_on_close_job()
            _assign_process_to_job(self._job_handle, int(proc._handle))  # type: ignore[attr-defined]
        except OSError:
            # Best-effort: if Job Object creation/assignment fails (rare —
            # nested jobs on pre-Win8, restricted desktops), fall back to
            # the ``proc.kill()`` path.  We must NOT raise here or
            # we would mask the user's command.
            self._close_handle()

    def terminate(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        """Kill the entire tree rooted at *proc*."""
        if proc.poll() is not None:
            self._close_handle()
            return
        try:
            if os.name == "nt":
                if self._job_handle is not None:
                    _terminate_job(self._job_handle)
                else:
                    proc.kill()
            else:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                try:
                    proc.wait(timeout=2)
                    return
                except subprocess.TimeoutExpired:
                    pass
                os.killpg(pgid, signal.SIGKILL)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        except (ProcessLookupError, OSError):
            pass
        finally:
            self._close_handle()

    def close(self) -> None:
        """Release the job handle once the child exits cleanly."""
        self._close_handle()

    def _close_handle(self) -> None:
        if self._job_handle is None:
            return
        handle = self._job_handle
        self._job_handle = None
        try:
            _close_handle(handle)
        except OSError:
            pass


if os.name == "nt":  # pragma: no cover - exercised on the Windows CI lane
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    # JobObjectExtendedLimitInformation = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _create_kill_on_close_job() -> int:
        handle = _kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _kernel32.SetInformationJobObject(
            handle,
            9,  # JobObjectExtendedLimitInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            err = ctypes.get_last_error()
            _kernel32.CloseHandle(handle)
            raise ctypes.WinError(err)  # type: ignore[attr-defined]
        return int(handle)

    def _assign_process_to_job(job_handle: int, process_handle: int) -> None:
        if not _kernel32.AssignProcessToJobObject(job_handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]

    def _terminate_job(job_handle: int) -> None:
        if not _kernel32.TerminateJobObject(job_handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]

    def _close_handle(handle: int) -> None:
        if not _kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]

else:

    def _create_kill_on_close_job() -> int:  # pragma: no cover - POSIX stub
        raise OSError("Job Objects are Windows-only")

    def _assign_process_to_job(job_handle: int, process_handle: int) -> None:  # pragma: no cover
        raise OSError("Job Objects are Windows-only")

    def _terminate_job(job_handle: int) -> None:  # pragma: no cover
        raise OSError("Job Objects are Windows-only")

    def _close_handle(handle: int) -> None:  # pragma: no cover
        raise OSError("Job Objects are Windows-only")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    *,
    timeout: float | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Run a subprocess, raising on failure or timeout.

    Honours the ambient :func:`timeout_budget` when *timeout* is None.
    On timeout the entire process tree is terminated (POSIX: ``killpg``
    on the new session; Windows: ``TerminateJobObject`` on a
    ``KILL_ON_JOB_CLOSE`` job) and :class:`subprocess.TimeoutExpired`
    is re-raised.

    When *on_line* is supplied, stdout and stderr are merged and the
    callback is invoked once per output line (with the trailing newline
    stripped) as the subprocess produces it. The lines are also
    re-emitted on the parent's stdout so the user-visible output is
    unchanged. When *on_line* is ``None`` the subprocess inherits the
    parent's stdio directly (legacy behaviour).
    """
    effective = _effective_timeout(timeout)
    if on_line is not None:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=(os.name != "nt"),
        )
    else:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            start_new_session=(os.name != "nt"),
        )
    container = _ProcessContainer()
    container.attach(proc)
    try:
        try:
            if on_line is not None and proc.stdout is not None:
                # Stream lines through the callback while still enforcing
                # the wall-clock timeout. We use ``select`` (POSIX) or a
                # blocking readline with a deadline check (Windows) so a
                # subprocess that stops producing newlines cannot escape
                # the budget.
                deadline = None if effective is None else time.monotonic() + effective
                stream = proc.stdout
                use_select = os.name != "nt"
                while True:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            container.terminate(proc)
                            raise subprocess.TimeoutExpired(cmd, effective)
                    else:
                        remaining = None
                    if use_select:
                        ready, _, _ = select.select(
                            [stream],
                            [],
                            [],
                            remaining if remaining is not None else None,
                        )
                        if not ready:
                            # select timed out -> deadline reached
                            container.terminate(proc)
                            raise subprocess.TimeoutExpired(cmd, effective)
                    raw = stream.readline()
                    if not raw:
                        break
                    text_line = raw.rstrip("\n")
                    try:
                        on_line(text_line)
                    except BaseException:
                        # Caller-supplied callback raised; tear down the
                        # subprocess tree before propagating so we don't
                        # leak processes (POSIX) or job-object handles
                        # (Windows).
                        container.terminate(proc)
                        raise
                    sys.stdout.write(raw)
                wait_timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
                rc = proc.wait(timeout=wait_timeout)
            else:
                rc = proc.wait(timeout=effective)
        except subprocess.TimeoutExpired:
            container.terminate(proc)
            raise subprocess.TimeoutExpired(cmd, effective) from None
        except KeyboardInterrupt:
            # ``start_new_session=True`` (POSIX) and the Job Object (Windows)
            # both isolate the child from our terminal's signals, so the
            # Ctrl-C the user typed does NOT propagate.  Kill the whole tree
            # before re-raising, otherwise hung builds/flashes keep running.
            container.terminate(proc)
            raise
    finally:
        container.close()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


def run_capture(
    cmd: list[str],
    cwd: Path | None = None,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture its text output.

    Same timeout / process-tree semantics as :func:`run`.
    """
    effective = _effective_timeout(timeout)
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name != "nt"),
    )
    container = _ProcessContainer()
    container.attach(proc)
    try:
        try:
            out, err = proc.communicate(timeout=effective)
        except subprocess.TimeoutExpired:
            container.terminate(proc)
            # Drain any buffered output so the caller can still log it.
            try:
                out, err = proc.communicate(timeout=1)
            except Exception:  # noqa: BLE001
                out, err = "", ""
            raise subprocess.TimeoutExpired(cmd, effective, output=out, stderr=err) from None
        except KeyboardInterrupt:
            # See note in :func:`run` — the child is isolated from our
            # terminal's SIGINT; tear the tree down before re-raising.
            container.terminate(proc)
            raise
    finally:
        container.close()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=out, stderr=err)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=out, stderr=err)


def print_captured_output(result: subprocess.CompletedProcess[str]) -> None:
    """Echo captured subprocess output to stdout/stderr."""

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")


def jlink_failure_hint(output: str) -> str | None:
    """Translate common SEGGER failures into clearer user-facing hints."""

    lowered = output.lower()
    if "failed to open dll" in lowered:
        return (
            "SEGGER J-Link failed to load its runtime library.\n"
            "Check that the J-Link tools are installed correctly and can run outside `nsx`."
        )
    if "connecting to j-link via usb...failed" in lowered or "cannot connect to j-link" in lowered:
        return (
            "SEGGER J-Link could not connect to the probe over USB.\n"
            "Check the probe connection, power, and that no other tool is holding the J-Link."
        )
    if "cannot connect to target" in lowered or "failed to connect to target" in lowered:
        return (
            "SEGGER J-Link connected, but could not connect to the target device.\n"
            "Check target power, SWD wiring, board selection, and reset state."
        )
    return None


def format_subprocess_error(exc: subprocess.CalledProcessError, *, context: str) -> str:
    """Format a subprocess failure for user-facing CLI output."""

    output_parts: list[str] = []
    stdout = getattr(exc, "stdout", None)
    stderr = getattr(exc, "stderr", None)
    if isinstance(stdout, str) and stdout.strip():
        output_parts.append(stdout.strip())
    if isinstance(stderr, str) and stderr.strip():
        output_parts.append(stderr.strip())
    combined_output = "\n".join(output_parts)

    verbose = _VERBOSITY.get()
    hint = jlink_failure_hint(combined_output)
    if hint:
        message = f"{context} failed.\n{hint}"
        if verbose == 0:
            message += "\nRe-run with `--verbose` for the full tool output."
        return message

    message = f"{context} failed with exit code {exc.returncode}."
    if verbose == 0:
        message += "\nRe-run with `--verbose` for the full subprocess traceback."
    return message


def git_clone(url: str, dest: Path, *, revision: str | None = None, depth: int = 1) -> None:
    """Clone a git repo into *dest*, optionally checking out a specific revision."""

    cmd = ["git", "clone", "--single-branch"]
    if revision:
        cmd += ["--branch", revision]
    if depth:
        cmd += ["--depth", str(depth)]
    cmd += [url, str(dest)]
    run(cmd)


def git_clone_at_commit(url: str, dest: Path, commit: str) -> None:
    """Clone *url* into *dest* and check out the exact *commit*.

    Used by ``nsx sync`` to faithfully restore the locked SHA, and by
    ``nsx_lock.hash_git_artifact`` to compute the upstream-artifact
    hash for git lock entries.

    Tries a shallow ``git fetch --depth 1 <commit>`` first to avoid
    transferring full history; this works on hosts that allow fetching
    arbitrary SHAs (modern GitHub does, with
    ``uploadpack.allowReachableSHA1InWant``). Falls back to a full
    clone + checkout when the server rejects the targeted fetch.
    """

    import os
    import stat

    def _on_rm_error(_func, _path, _exc_info):  # noqa: ANN001
        # git pack/index files can be read-only on Windows; clear the
        # write bit and retry the original failing op (which may be
        # ``os.unlink`` for files or ``os.rmdir`` for directories) so
        # rmtree can finish in both cases. On Python 3.12+ rmtree may
        # call fd-based syscalls (e.g. ``os.open(path, flags)``) that
        # require multiple positional args; in that case ``_func(_path)``
        # raises TypeError, which we swallow.
        try:
            os.chmod(_path, stat.S_IWRITE)
        except OSError:
            pass
        try:
            _func(_path)
        except (OSError, TypeError):
            pass

    def _robust_rmtree(path: Path) -> None:
        import shutil

        if not path.exists():
            return
        # ``onerror=`` is deprecated in 3.12 and removed in 3.14. The
        # callback ignores the third arg's shape so it works for both APIs.
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_on_rm_error)
        else:
            shutil.rmtree(path, onerror=_on_rm_error)

    # Match ``git clone`` semantics: fail-fast on stale state. If
    # ``dest`` already exists we remove it up front so neither
    # ``git init`` nor the fallback ``git clone`` has to reason about
    # leftover files from a prior interrupted run.
    _robust_rmtree(dest)
    if dest.exists():
        from ._errors import NSXResolutionError

        raise NSXResolutionError(
            f"git_clone_at_commit: refusing to operate on non-empty path {dest}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        run(["git", "init", "--quiet", str(dest)])
        run(["git", "remote", "add", "origin", url], cwd=dest)
        run(["git", "fetch", "--depth", "1", "--quiet", "origin", commit], cwd=dest)
        run(["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"], cwd=dest)
    except subprocess.CalledProcessError:
        # Server doesn't allow fetching arbitrary SHAs, or commit is
        # unreachable from any ref tip. Fall back to a full clone.
        _robust_rmtree(dest)
        if dest.exists():
            from ._errors import NSXResolutionError

            raise NSXResolutionError(
                f"git_clone_at_commit: failed to remove stale partial clone at {dest}"
            )
        run(["git", "clone", url, str(dest)])
        run(["git", "checkout", "--detach", commit], cwd=dest)


def git_fetch(repo: Path, *, remote: str = "origin") -> None:
    """Fetch updates from the remote in an existing clone."""

    run(["git", "fetch", remote], cwd=repo)


def git_checkout(repo: Path, revision: str) -> None:
    """Check out a specific revision in an existing clone."""

    run(["git", "checkout", revision], cwd=repo)


def git_current_sha(repo: Path) -> str | None:
    """Return the HEAD SHA of *repo*, or ``None`` on failure."""

    try:
        result = run_capture(["git", "rev-parse", "HEAD"], cwd=repo)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def extract_view_command(build_dir: Path, target: str) -> list[str]:
    """Extract the SWO viewer command for a Ninja target from ``build.ninja``."""

    ninja_file = build_dir / "build.ninja"
    if not ninja_file.exists():
        from ._errors import NSXConfigError

        raise NSXConfigError(f"Missing build.ninja in build directory: {build_dir}")

    lines = ninja_file.read_text(encoding="utf-8").splitlines()
    block_header = f"build CMakeFiles/{target}"
    for idx, line in enumerate(lines):
        if not line.strip().startswith(block_header):
            continue
        for follow in lines[idx + 1 : idx + 8]:
            stripped = follow.strip()
            if stripped.startswith("COMMAND = "):
                command_text = stripped.removeprefix("COMMAND = ")
                if " && " in command_text:
                    _, command_text = command_text.split(" && ", 1)
                return shlex.split(command_text, posix=(os.name != "nt"))
        break

    from ._errors import NSXConfigError

    raise NSXConfigError(
        f"Unable to resolve the SEGGER SWO viewer command for target '{target}' from {ninja_file}"
    )
