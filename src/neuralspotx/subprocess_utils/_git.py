"""Git transport hardening + git wrapper helpers.

All ``git`` subprocesses that consume registry-supplied URLs go through
this module so URL validation and protocol-allow-list flags are
applied consistently.
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
import sys
import time
from pathlib import Path

_log = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Transient-failure retry for git *network* operations
# ---------------------------------------------------------------------------
#
# ``git ls-remote`` / ``git fetch`` / ``git clone`` reach out over the
# network and occasionally fail for reasons unrelated to the request: a
# DNS hiccup, a dropped TLS handshake, a GitHub 5xx/429, a reset
# connection. These are exactly the "random, transient" failures that
# make ``nsx lock`` flaky on busy networks and in CI. The helpers below
# wrap each network invocation in a bounded exponential-backoff retry
# that only re-attempts when the captured error text matches a known
# transient signature, so deterministic failures (bad URL, unknown ref,
# auth, or the expected "unadvertised object" rejection that drives the
# shallow-fetch fallback) still fail fast.

# Substrings (compared case-insensitively against captured stderr/output)
# that mark a git failure as a transient transport error worth retrying.
# Curated to avoid matching deterministic failures.
_TRANSIENT_GIT_ERROR_PATTERNS: tuple[str, ...] = (
    "could not resolve host",
    "couldn't resolve host",
    "temporary failure in name resolution",
    "connection timed out",
    "connection reset",
    "connection refused",
    "operation timed out",
    "gateway time-out",
    "gateway timeout",
    "early eof",
    "rpc failed",
    "remote end hung up",
    "unable to access",
    "failed to connect",
    "transfer closed",
    "unexpected disconnect",
    "gnutls",
    "ssl connect error",
    "ssl_error",
    "tls handshake",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "too many requests",
    "returned error: 408",
    "returned error: 429",
    "returned error: 500",
    "returned error: 502",
    "returned error: 503",
    "returned error: 504",
)


# Substrings that mark a failure as *permanent* (deterministic) and never
# worth retrying, checked ahead of the transient patterns above. Some
# transient signatures are broad on purpose (e.g. ``unable to access`` —
# the curl prefix that also wraps genuinely transient DNS/connection
# errors), so this deny-list takes precedence to keep an authentication
# or HTTP 4xx failure (which carries that same prefix) failing fast.
_PERMANENT_GIT_ERROR_PATTERNS: tuple[str, ...] = (
    "authentication failed",
    "invalid username or password",
    "repository not found",
    "could not read from remote repository",
    "permission denied",
    "access denied",
    "denied to",
    "returned error: 400",
    "returned error: 401",
    "returned error: 403",
    "returned error: 404",
    "returned error: 451",
)


# Indirection so tests can disable real sleeping between retries.
_sleep = time.sleep


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _git_retry_config() -> tuple[int, float, float]:
    """Return ``(attempts, base_delay, max_delay)`` from the environment.

    ``NSX_GIT_RETRIES`` (default 3, clamped to 1-10) is the *total*
    number of attempts; set it to ``1`` to disable retries.
    ``NSX_GIT_RETRY_BASE_DELAY`` (default 0.5s) is the first backoff
    delay; subsequent delays grow exponentially with added jitter.
    ``NSX_GIT_RETRY_MAX_DELAY`` (default 8s) caps each backoff so a high
    retry count — or a lockfile that resolves many repos — cannot stack
    up into multi-minute stalls.
    """

    attempts = _env_int("NSX_GIT_RETRIES", 3, minimum=1, maximum=10)
    base = _env_float("NSX_GIT_RETRY_BASE_DELAY", 0.5, minimum=0.0)
    max_delay = _env_float("NSX_GIT_RETRY_MAX_DELAY", 8.0, minimum=0.0)
    return attempts, base, max_delay


def _git_lowspeed_flags() -> tuple[str, ...]:
    """``-c`` flags that abort a *stalled* HTTP(S) transfer.

    ``http.lowSpeedLimit`` (bytes/sec) + ``http.lowSpeedTime`` (seconds)
    tell git to abort when throughput stays below the limit for the
    given window. Unlike a blunt wall-clock deadline this never kills a
    slow-but-progressing clone (e.g. a large SDK over a thin link) — it
    only fires once the transfer has effectively stalled, surfacing as a
    ``transfer closed`` / ``RPC failed`` error that the retry layer
    classifies as transient. Tunable via ``NSX_GIT_LOW_SPEED_LIMIT`` /
    ``NSX_GIT_LOW_SPEED_TIME``; set either to 0 to disable. Ignored by
    git for non-HTTP transports.
    """

    limit = _env_int("NSX_GIT_LOW_SPEED_LIMIT", 1000, minimum=0, maximum=1_000_000_000)
    secs = _env_int("NSX_GIT_LOW_SPEED_TIME", 60, minimum=0, maximum=86_400)
    if limit <= 0 or secs <= 0:
        return ()
    return (
        "-c",
        f"http.lowSpeedLimit={limit}",
        "-c",
        f"http.lowSpeedTime={secs}",
    )


def _git_net_flags() -> tuple[str, ...]:
    """Hardening + stall-abort ``-c`` flags for git *network* commands."""

    return (*GIT_PROTOCOL_ALLOWLIST_FLAGS, *_git_lowspeed_flags())


def _git_default_timeout() -> float | None:
    """Generous per-attempt wall-clock backstop for a hung git network op.

    The low-speed guard (:func:`_git_lowspeed_flags`) catches a stalled
    *transfer*, but not a hang during DNS/connect/TLS, nor an SSH remote
    where the HTTP low-speed config does not apply. ``NSX_GIT_TIMEOUT``
    (default 600s / 10 min) bounds those so a half-open connection can't
    wedge ``nsx lock`` forever; once it fires the resulting
    ``TimeoutExpired`` is retried like any other transient failure.
    Deliberately generous — a large SDK over a slow link can take many
    minutes — and tunable; set to 0 to disable. An explicit ``--timeout``
    / ``timeout_budget`` always takes precedence.
    """

    return _env_float("NSX_GIT_TIMEOUT", 600.0, minimum=0.0) or None


def _net_timeout() -> float | None:
    """Resolve the wall-clock timeout for a single git network attempt.

    An explicit ambient budget (the user's ``--timeout``) always wins;
    otherwise fall back to the generous :func:`_git_default_timeout`
    backstop.
    """

    from ._verbosity import _effective_timeout

    ambient = _effective_timeout(None)
    return ambient if ambient is not None else _git_default_timeout()


def _git_error_text(exc: BaseException) -> str:
    parts: list[str] = []
    for attr in ("stderr", "output"):
        val = getattr(exc, attr, None)
        if isinstance(val, bytes):
            val = val.decode("utf-8", "replace")
        if val:
            parts.append(str(val))
    return " ".join(parts).lower()


def _is_transient_git_error(exc: BaseException) -> bool:
    """Return True when *exc* looks like a retryable transport failure."""

    if isinstance(exc, subprocess.TimeoutExpired):
        return True
    text = _git_error_text(exc)
    if not text:
        # No diagnostic text was captured. We can't positively classify
        # the failure, but a silent git network op is far more likely to
        # be a transient blip (killed connection, abrupt disconnect) than
        # a deterministic error — those almost always print a ``fatal:``
        # line. Permanent, deterministic problems (bad URL/protocol) are
        # rejected up front by _validate_git_url as NSXGitError, which
        # this retry path never catches. So retry on empty output.
        return True
    # A permanent signature wins even when a broad transient pattern (e.g.
    # ``unable to access``) would otherwise match, so auth / HTTP 4xx
    # failures fail fast instead of burning the full retry budget.
    if any(pat in text for pat in _PERMANENT_GIT_ERROR_PATTERNS):
        return False
    return any(pat in text for pat in _TRANSIENT_GIT_ERROR_PATTERNS)


def _git_network_retry(operation, *, label, before_retry=None):  # type: ignore[no-untyped-def]
    """Run *operation* (a no-arg callable), retrying transient failures.

    *operation* performs a single git network invocation and must raise
    :class:`subprocess.CalledProcessError` /
    :class:`subprocess.TimeoutExpired` on failure (carrying ``stderr`` /
    ``output`` so the failure can be classified). Non-transient failures
    and the final attempt re-raise unchanged. *before_retry*, when given,
    is invoked after the backoff sleep and before the next attempt (used
    to clear a partially-populated clone directory).
    """

    attempts, base, max_delay = _git_retry_config()
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if attempt >= attempts or not _is_transient_git_error(exc):
                raise
            # Exponential backoff, capped at ``max_delay`` so many repos
            # (or a high NSX_GIT_RETRIES) can't stack into long stalls,
            # plus jitter to avoid a synchronised retry stampede when the
            # parallel prefetch fans out across remotes. The final ``min``
            # keeps the jittered value within the cap.
            backoff = min(base * (2 ** (attempt - 1)), max_delay)
            delay = min(max_delay, backoff + random.uniform(0.0, base))
            _log.warning(
                "transient git error during %s (attempt %d/%d), retrying in %.1fs",
                label,
                attempt,
                attempts,
                delay,
            )
            _sleep(delay)
            if before_retry is not None:
                before_retry()
    raise AssertionError("unreachable")  # pragma: no cover


def _on_rm_error(_func, _path, _exc_info):  # noqa: ANN001
    # git pack/index files can be read-only on Windows; clear the write
    # bit and retry the original failing op (which may be ``os.unlink``
    # for files or ``os.rmdir`` for directories) so rmtree can finish in
    # both cases. On Python 3.12+ rmtree may call fd-based syscalls (e.g.
    # ``os.open(path, flags)``) that require multiple positional args; in
    # that case ``_func(_path)`` raises TypeError, which we swallow.
    import stat

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
    # ``onerror=`` is deprecated in 3.12 and removed in 3.14. The callback
    # ignores the third arg's shape so it works for both APIs.
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:
        shutil.rmtree(path, onerror=_on_rm_error)


def _run_net(cmd, cwd=None):  # type: ignore[no-untyped-def]
    """Run a streaming git network command, capturing its output so a
    transient failure can be classified while still echoing live output.

    The streamed lines are buffered and, on failure, attached to the
    :class:`subprocess.CalledProcessError` (which carries no ``stderr``
    when the subprocess inherits the parent's stdio) so
    :func:`_is_transient_git_error` can inspect them.
    """

    captured: list[str] = []
    try:
        _run(cmd, cwd=cwd, on_line=captured.append, timeout=_net_timeout())
    except subprocess.CalledProcessError as exc:
        if not getattr(exc, "stderr", None):
            exc.stderr = "\n".join(captured)
        raise


def git_clone(url: str, dest: Path, *, revision: str | None = None, depth: int = 1) -> None:
    """Clone a git repo into *dest*, optionally checking out a specific revision."""

    _validate_git_url(url)
    cmd = ["git", *_git_net_flags(), "clone", "--single-branch"]
    if revision:
        cmd += ["--branch", revision]
    if depth:
        cmd += ["--depth", str(depth)]
    cmd += [url, str(dest)]
    _git_network_retry(
        lambda: _run_net(cmd),
        label="git clone",
        before_retry=lambda: _robust_rmtree(dest),
    )


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
        _git_network_retry(
            lambda: _run_net(
                [
                    "git",
                    *_git_net_flags(),
                    "fetch",
                    "--depth",
                    "1",
                    "--quiet",
                    "origin",
                    commit,
                ],
                cwd=dest,
            ),
            label="git fetch",
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
        _git_network_retry(
            lambda: _run_net(["git", *_git_net_flags(), "clone", url, str(dest)]),
            label="git clone",
            before_retry=lambda: _robust_rmtree(dest),
        )
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
    cmd = ["git", *_git_net_flags(), "ls-remote", url, *refs]
    return _git_network_retry(
        lambda: _run_capture(cmd, timeout=_net_timeout()), label="git ls-remote"
    )
