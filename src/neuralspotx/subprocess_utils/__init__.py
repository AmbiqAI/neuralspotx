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

This package is split into mechanical submodules:

* :mod:`._verbosity` — verbosity / timeout-budget context vars.
* :mod:`._winjob` — Windows Job Object machinery for process-tree
  containment (``_ProcessContainer``).
* :mod:`._runner` — :func:`run`, :func:`run_capture`, error formatting.
* :mod:`._git` — git transport hardening + git wrapper helpers.

The names exported here are the stable public surface; importing from
the underscored submodules is allowed but not part of the supported API.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from ._git import (
    _ALLOWED_GIT_URL_SCHEMES,
    GIT_PROTOCOL_ALLOWLIST_FLAGS,
    _validate_git_url,
    git_checkout,
    git_clone,
    git_clone_at_commit,
    git_current_sha,
    git_fetch,
    git_ls_remote,
)
from ._runner import (
    _ProcessContainer,
    format_subprocess_error,
    jlink_failure_hint,
    print_captured_output,
    run,
    run_capture,
)
from ._verbosity import (
    _TIMEOUT,
    _VERBOSITY,
    _effective_timeout,
    get_verbosity,
    set_verbosity,
    timeout_budget,
    verbosity,
)


def extract_view_command(build_dir: Path, target: str) -> list[str]:
    """Extract the SWO viewer command for a Ninja target from ``build.ninja``."""

    ninja_file = build_dir / "build.ninja"
    if not ninja_file.exists():
        from .._errors import NSXConfigError

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

    from .._errors import NSXConfigError

    raise NSXConfigError(
        f"Unable to resolve the SEGGER SWO viewer command for target '{target}' from {ninja_file}"
    )


__all__ = [
    "GIT_PROTOCOL_ALLOWLIST_FLAGS",
    "extract_view_command",
    "format_subprocess_error",
    "get_verbosity",
    "git_checkout",
    "git_clone",
    "git_clone_at_commit",
    "git_current_sha",
    "git_fetch",
    "git_ls_remote",
    "jlink_failure_hint",
    "print_captured_output",
    "run",
    "run_capture",
    "set_verbosity",
    "timeout_budget",
    "verbosity",
]
