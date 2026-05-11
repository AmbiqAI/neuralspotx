"""Per-subprocess process-tree containment.

POSIX gets process-tree termination "for free" via ``start_new_session=True``
+ ``killpg``: every grandchild inherits the new process group, so one
``killpg(SIGKILL)`` reaps ``cmake``, ``ninja``, ``cl.exe``, link.exe, etc.

Windows has no such inheritance.  ``proc.kill()`` only terminates the
direct child, so a hung ``cmake`` would leave ``ninja`` and the compiler
running in the background — the "ghost ninja" problem.

The Win32 fix is a Job Object with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``:
any process assigned to the job (and every descendant it spawns) is
guaranteed to die when the job handle is closed or ``TerminateJobObject``
is called.  We attach the child immediately after ``Popen`` and keep the
handle alive until ``_close_container`` is called from the wait/teardown
path.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess


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
