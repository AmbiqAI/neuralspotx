"""Helpers for subprocess execution and tool-specific error formatting."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

_VERBOSE = 0


def set_verbosity(level: int) -> None:
    """Set subprocess helper verbosity."""

    global _VERBOSE
    _VERBOSE = level


def run(cmd: list[str], cwd: Path | None = None) -> None:
    """Run a subprocess and raise on failure."""

    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def run_capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and capture its text output."""

    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )


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

    hint = jlink_failure_hint(combined_output)
    if hint:
        message = f"{context} failed.\n{hint}"
        if _VERBOSE == 0:
            message += "\nRe-run with `--verbose` for the full tool output."
        return message

    message = f"{context} failed with exit code {exc.returncode}."
    if _VERBOSE == 0:
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
        # rmtree can finish in both cases.
        try:
            os.chmod(_path, stat.S_IWRITE)
            _func(_path)
        except OSError:
            pass

    def _robust_rmtree(path: Path) -> None:
        import shutil

        if path.exists():
            shutil.rmtree(path, onerror=_on_rm_error)

    # Match ``git clone`` semantics: fail-fast on stale state. If
    # ``dest`` already exists we remove it up front so neither
    # ``git init`` nor the fallback ``git clone`` has to reason about
    # leftover files from a prior interrupted run.
    _robust_rmtree(dest)
    if dest.exists():
        raise SystemExit(f"git_clone_at_commit: refusing to operate on non-empty path {dest}")
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
            raise SystemExit(f"git_clone_at_commit: failed to remove stale partial clone at {dest}")
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
        raise SystemExit(f"Missing build.ninja in build directory: {build_dir}")

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

    raise SystemExit(
        f"Unable to resolve the SEGGER SWO viewer command for target '{target}' from {ninja_file}"
    )
