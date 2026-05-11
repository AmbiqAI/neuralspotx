"""Git transport hardening + git wrapper helpers.

All ``git`` subprocesses that consume registry-supplied URLs go through
this module so URL validation and protocol-allow-list flags are
applied consistently.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(cmd, **kwargs):  # type: ignore[no-untyped-def]
    # Look ``run`` up on the facade module so monkeypatches such as
    # ``monkeypatch.setattr(subprocess_utils, "run", fake_run)`` continue
    # to intercept git helpers after the package was split.
    from . import run as _facade_run

    return _facade_run(cmd, **kwargs)


def _run_capture(cmd, **kwargs):  # type: ignore[no-untyped-def]
    from . import run_capture as _facade_run_capture

    return _facade_run_capture(cmd, **kwargs)


# ``-c`` overrides applied to every ``git`` invocation that consumes a
# registry-supplied URL. ``protocol.allow=user`` raises the default
# permission level required for non-built-in transports to "user", and
# the explicit ``ext`` / ``file`` denies refuse the two transports that
# treat their URL component as code or as a local-filesystem path:
#
#   * ``ext::<cmd>`` runs ``<cmd>`` as a smart-transport remote helper
#     (CVE-2017-1000117 class).
#   * ``file://`` / ``file::`` reads from the local filesystem, which a
#     malicious registry entry could use to exfiltrate or stage content.
#
# Combined with :func:`_validate_git_url` (an early Python-side
# allow-list check), this gives defence in depth: the URL is rejected
# in-process before ``git`` is invoked, *and* ``git`` itself is told to
# refuse the same transports if the check is ever bypassed.
GIT_PROTOCOL_ALLOWLIST_FLAGS: tuple[str, ...] = (
    "-c",
    "protocol.allow=user",
    "-c",
    "protocol.ext.allow=never",
    "-c",
    "protocol.file.allow=never",
)


# Schemes accepted by :func:`_validate_git_url`. Anything else is
# refused outright (most importantly ``ext::``, ``file://``,
# ``file::``).  Includes ``git+https`` / ``git+ssh`` for parity with
# pip-style URLs that some registries emit.
_ALLOWED_GIT_URL_SCHEMES: frozenset[str] = frozenset({
    "http",
    "https",
    "ssh",
    "git",
    "git+http",
    "git+https",
    "git+ssh",
})


def _validate_git_url(url: str) -> None:
    """Refuse URLs that name a disallowed git transport.

    Raises :class:`NSXGitError` for ``ext::``, ``file://``, ``file::``,
    or any other transport not in :data:`_ALLOWED_GIT_URL_SCHEMES`.
    Bare ``git@host:path`` SCP-style URLs are accepted (treated as
    SSH).
    """

    from .._errors import NSXGitError

    if not isinstance(url, str) or not url:
        raise NSXGitError(f"git: refusing empty URL ({url!r})")

    lowered = url.lower()
    # Refuse remote-helper transports explicitly. ``git`` parses
    # ``<helper>::<rest>`` ahead of any scheme, so e.g. ``ext::sh -c
    # ...`` and ``file::/tmp/x`` bypass urlparse-based scheme checks.
    if "::" in url:
        helper, _, _ = url.partition("::")
        # ``git+ssh::`` etc. are not real helpers; only refuse if the
        # prefix matches a known helper name. Block both ``ext`` and
        # ``file`` (the two transports we explicitly disallow), plus a
        # generic catch-all so a future registry typo can't sneak in
        # ``ftp::`` or ``mailto::``.
        if helper.lower() in {"ext", "file"} or "/" not in helper:
            raise NSXGitError(
                f"git: refusing URL {url!r}: disallowed remote-helper "
                f"protocol {helper!r}. Allowed protocols: "
                f"{sorted(_ALLOWED_GIT_URL_SCHEMES)} (or git@host:path)."
            )

    # SCP-style ``[user@]host:path`` (no ``://``); accept only that
    # form and reject bare local filesystem paths so the allow-list
    # cannot be sidestepped by handing git a path argument.
    if "://" not in url:
        if url.startswith("file:") or lowered.startswith("file:"):
            raise NSXGitError(f"git: refusing URL {url!r}: disallowed protocol 'file'.")
        # Reject obvious local-path forms before SCP-style detection:
        # POSIX absolute (``/``), home (``~``), explicit relative
        # (``./``, ``../``), and Windows drive prefixes (``C:\``,
        # ``C:/``). Note: ``C:foo`` (drive letter + colon, no slash)
        # is also a local path on Windows but indistinguishable from
        # ``host:path`` without OS context — we reject it conservatively.
        if url.startswith(("/", "~", "./", "../", ".\\", "..\\")):
            raise NSXGitError(
                f"git: refusing URL {url!r}: looks like a local filesystem "
                "path. Allowed protocols: "
                f"{sorted(_ALLOWED_GIT_URL_SCHEMES)} (or git@host:path)."
            )
        if len(url) >= 3 and url[0].isalpha() and url[1] == ":" and url[2] in ("\\", "/"):
            raise NSXGitError(f"git: refusing URL {url!r}: looks like a Windows drive path.")
        # Require SCP-style ``[user@]host:path`` form: a single ``:``
        # separating a non-empty host from a non-empty path, host must
        # not contain ``/``.
        if ":" not in url:
            raise NSXGitError(
                f"git: refusing URL {url!r}: not a recognised remote. "
                f"Allowed protocols: {sorted(_ALLOWED_GIT_URL_SCHEMES)} "
                "(or git@host:path)."
            )
        host_part, _, path_part = url.partition(":")
        if not host_part or not path_part or "/" in host_part:
            raise NSXGitError(
                f"git: refusing URL {url!r}: not a valid SCP-style remote "
                "(expected ``[user@]host:path``)."
            )
        return

    scheme = lowered.split("://", 1)[0]
    if scheme not in _ALLOWED_GIT_URL_SCHEMES:
        raise NSXGitError(
            f"git: refusing URL {url!r}: disallowed protocol {scheme!r}. "
            f"Allowed protocols: {sorted(_ALLOWED_GIT_URL_SCHEMES)} "
            "(or git@host:path)."
        )


def git_clone(url: str, dest: Path, *, revision: str | None = None, depth: int = 1) -> None:
    """Clone a git repo into *dest*, optionally checking out a specific revision."""

    _validate_git_url(url)
    cmd = ["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "clone", "--single-branch"]
    if revision:
        cmd += ["--branch", revision]
    if depth:
        cmd += ["--depth", str(depth)]
    cmd += [url, str(dest)]
    _run(cmd)


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
    _validate_git_url(url)
    _robust_rmtree(dest)
    if dest.exists():
        from .._errors import NSXResolutionError

        raise NSXResolutionError(
            f"git_clone_at_commit: refusing to operate on non-empty path {dest}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        _run(["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "init", "--quiet", str(dest)])
        _run(
            ["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "remote", "add", "origin", url],
            cwd=dest,
        )
        _run(
            [
                "git",
                *GIT_PROTOCOL_ALLOWLIST_FLAGS,
                "fetch",
                "--depth",
                "1",
                "--quiet",
                "origin",
                commit,
            ],
            cwd=dest,
        )
        _run(
            ["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "checkout", "--detach", "--quiet", "FETCH_HEAD"],
            cwd=dest,
        )
    except subprocess.CalledProcessError:
        # Server doesn't allow fetching arbitrary SHAs, or commit is
        # unreachable from any ref tip. Fall back to a full clone.
        _robust_rmtree(dest)
        if dest.exists():
            from .._errors import NSXResolutionError

            raise NSXResolutionError(
                f"git_clone_at_commit: failed to remove stale partial clone at {dest}"
            )
        _run(["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "clone", url, str(dest)])
        _run(["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "checkout", "--detach", commit], cwd=dest)


def git_fetch(repo: Path, *, remote: str = "origin") -> None:
    """Fetch updates from the remote in an existing clone."""

    _run(["git", "fetch", remote], cwd=repo)


def git_checkout(repo: Path, revision: str) -> None:
    """Check out a specific revision in an existing clone."""

    _run(["git", "checkout", revision], cwd=repo)


def git_current_sha(repo: Path) -> str | None:
    """Return the HEAD SHA of *repo*, or ``None`` on failure."""

    try:
        result = _run_capture(["git", "rev-parse", "HEAD"], cwd=repo)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def git_ls_remote(url: str, *refs: str) -> subprocess.CompletedProcess[str]:
    """Run ``git ls-remote`` against *url* with transport hardening.

    Validates *url* against the registry-URL allow-list (refusing
    ``ext::``, ``file://``, ``file::``, and other disallowed
    transports) and prefixes the invocation with
    :data:`GIT_PROTOCOL_ALLOWLIST_FLAGS` so a malicious URL cannot
    bypass the in-process check via a transport ``git`` would
    otherwise honour. Returns the :class:`subprocess.CompletedProcess`
    from :func:`run_capture`.
    """

    _validate_git_url(url)
    cmd = ["git", *GIT_PROTOCOL_ALLOWLIST_FLAGS, "ls-remote", url, *refs]
    return _run_capture(cmd)
