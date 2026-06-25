"""Phase 5 — git transport hardening.

Verifies that NSX refuses to operate on disallowed git transports
(``ext::``, ``file::``, ``file://``) and that every ``git`` invocation
carries the protocol allow-list ``-c`` overrides.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from neuralspotx import NSXGitError, subprocess_utils
from neuralspotx.subprocess_utils import (
    GIT_PROTOCOL_ALLOWLIST_FLAGS,
    _validate_git_url,
    git_clone,
    git_clone_at_commit,
    git_ls_remote,
)


class TestValidateGitUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/foo.git",
            "http://example.com/foo.git",
            "ssh://git@github.com/foo/bar.git",
            "git+https://example.com/foo.git",
            "git@github.com:foo/bar.git",  # SCP-style
        ],
    )
    def test_accepts_allowed_schemes(self, url: str) -> None:
        _validate_git_url(url)  # must not raise

    @pytest.mark.parametrize(
        "url",
        [
            "ext::sh -c id",
            "ext::/usr/bin/id",
            "file:///tmp/evil",
            "file::/tmp/evil",
            "ftp://example.com/foo.git",
        ],
    )
    def test_rejects_disallowed_protocols(self, url: str) -> None:
        with pytest.raises(NSXGitError) as excinfo:
            _validate_git_url(url)
        # The error message should mention "protocol".
        assert "protocol" in str(excinfo.value).lower()

    def test_rejects_empty_url(self) -> None:
        with pytest.raises(NSXGitError):
            _validate_git_url("")

    @pytest.mark.parametrize(
        "url",
        [
            "/tmp/repo",
            "../repo",
            "./repo",
            "~/repo",
            "C:\\repo",
            "C:/repo",
            "just-a-name",  # no scheme, no SCP colon
            ":no-host",  # empty host
            "host:",  # empty path
            "host/with/slash:path",  # slash in host part
        ],
    )
    def test_rejects_local_filesystem_paths(self, url: str) -> None:
        with pytest.raises(NSXGitError):
            _validate_git_url(url)


class TestProtocolAllowListFlags:
    """Every git invocation must be prefixed with the allow-list overrides."""

    def test_flags_constant_shape(self) -> None:
        assert "-c" in GIT_PROTOCOL_ALLOWLIST_FLAGS
        joined = " ".join(GIT_PROTOCOL_ALLOWLIST_FLAGS)
        assert "protocol.allow=user" in joined
        assert "protocol.ext.allow=never" in joined
        assert "protocol.file.allow=never" in joined

    def test_git_clone_at_commit_uses_allow_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        invocations: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            invocations.append(list(cmd))

        monkeypatch.setattr(subprocess_utils, "run", fake_run)

        dest = tmp_path / "clone"
        git_clone_at_commit("https://example.com/foo.git", dest, "deadbeef")

        assert invocations, "expected at least one git invocation"
        for cmd in invocations:
            assert cmd[0] == "git"
            for flag in GIT_PROTOCOL_ALLOWLIST_FLAGS:
                assert flag in cmd, f"missing allow-list flag {flag} in {cmd}"

    def test_git_clone_uses_allow_list(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        invocations: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            invocations.append(list(cmd))

        monkeypatch.setattr(subprocess_utils, "run", fake_run)

        git_clone("https://example.com/foo.git", tmp_path / "x", revision="main")

        assert invocations and invocations[0][0] == "git"
        for flag in GIT_PROTOCOL_ALLOWLIST_FLAGS:
            assert flag in invocations[0]


class TestRefusesUnsafeUrls:
    def test_git_clone_at_commit_refuses_ext_url(self, tmp_path: Path) -> None:
        with pytest.raises(NSXGitError) as exc:
            git_clone_at_commit("ext::sh -c id", tmp_path / "x", "deadbeef")
        assert "protocol" in str(exc.value).lower()
        assert not (tmp_path / "x").exists()

    def test_git_clone_at_commit_refuses_file_url(self, tmp_path: Path) -> None:
        with pytest.raises(NSXGitError):
            git_clone_at_commit("file:///tmp/x", tmp_path / "x", "deadbeef")
        assert not (tmp_path / "x").exists()

    def test_git_clone_refuses_ext_url(self, tmp_path: Path) -> None:
        with pytest.raises(NSXGitError):
            git_clone("ext::sh -c id", tmp_path / "x")


class TestGitLsRemote:
    """``git_ls_remote`` is the hardened wrapper used by lock resolution."""

    def test_uses_allow_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        invocations: list[list[str]] = []

        class _FakeResult:
            stdout = ""

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            invocations.append(list(cmd))
            return _FakeResult()

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        git_ls_remote("https://example.com/foo.git", "main", "main^{}")

        assert invocations and invocations[0][0] == "git"
        for flag in GIT_PROTOCOL_ALLOWLIST_FLAGS:
            assert flag in invocations[0]
        # Must include "ls-remote" subcommand and the URL.
        assert "ls-remote" in invocations[0]
        assert "https://example.com/foo.git" in invocations[0]

    @pytest.mark.parametrize(
        "url",
        [
            "ext::sh -c id",
            "file:///tmp/evil",
            "file::/tmp/evil",
            "ftp://example.com/foo.git",
        ],
    )
    def test_refuses_disallowed_url(self, url: str) -> None:
        with pytest.raises(NSXGitError):
            git_ls_remote(url, "main")

    def test_resolve_ref_uses_hardened_ls_remote(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``nsx_lock.resolve_ref`` must refuse disallowed transports."""
        from neuralspotx.nsx_lock._resolution import ResolutionError, resolve_ref

        with pytest.raises(ResolutionError) as exc_info:
            resolve_ref("ext::sh -c id", "main", bypass_cache=True)
        assert isinstance(exc_info.value.__cause__, NSXGitError)


class TestTransientErrorClassification:
    """:func:`_is_transient_git_error` must retry transport blips only."""

    @pytest.mark.parametrize(
        "stderr",
        [
            "fatal: unable to access 'https://x/': Could not resolve host: x",
            "error: RPC failed; curl 56 Recv failure: Connection reset by peer",
            "fatal: the remote end hung up unexpectedly",
            "fatal: unable to access 'https://x/': The requested URL returned error: 503",
            "fatal: unable to access 'https://x/': The requested URL returned error: 429",
            "fetch-pack: protocol error: early EOF",
            "ssl_error_syscall",
            "fatal: unable to access 'https://x/': Operation timed out",
        ],
    )
    def test_transient_stderr_is_retryable(self, stderr: str) -> None:
        from neuralspotx.subprocess_utils import _git

        exc = subprocess.CalledProcessError(128, ["git"], stderr=stderr)
        assert _git._is_transient_git_error(exc) is True

    @pytest.mark.parametrize(
        "stderr",
        [
            "remote: Repository not found.\nfatal: repository 'https://x/' not found",
            "fatal: Authentication failed for 'https://x/'",
            "fatal: couldn't find remote ref refs/heads/nope",
            "fatal: remote error: upload-pack: not our ref deadbeef",
            "Server does not allow request for unadvertised object deadbeef",
        ],
    )
    def test_deterministic_stderr_is_not_retryable(self, stderr: str) -> None:
        from neuralspotx.subprocess_utils import _git

        exc = subprocess.CalledProcessError(128, ["git"], stderr=stderr)
        assert _git._is_transient_git_error(exc) is False

    def test_no_diagnostic_text_is_retryable(self) -> None:
        # A silent git network failure is far more likely a transient
        # blip than a deterministic error (which prints a ``fatal:`` line),
        # so we retry when no stderr/output was captured.
        from neuralspotx.subprocess_utils import _git

        exc = subprocess.CalledProcessError(128, ["git"])
        assert _git._is_transient_git_error(exc) is True

    def test_timeout_is_retryable(self) -> None:
        from neuralspotx.subprocess_utils import _git

        exc = subprocess.TimeoutExpired(["git"], 5.0)
        assert _git._is_transient_git_error(exc) is True


class TestNetworkRetry:
    """The git network helpers must retry transient failures."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from neuralspotx.subprocess_utils import _git

        monkeypatch.setattr(_git, "_sleep", lambda _delay: None)

    def test_ls_remote_retries_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        class _Result:
            stdout = "deadbeef\trefs/heads/main\n"

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] < 3:
                raise subprocess.CalledProcessError(
                    128,
                    list(cmd),
                    stderr="fatal: unable to access: Could not resolve host: github.com",
                )
            return _Result()

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        result = git_ls_remote("https://example.com/foo.git", "main")
        assert calls["n"] == 3
        assert result.stdout.startswith("deadbeef")

    def test_ls_remote_does_not_retry_deterministic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            raise subprocess.CalledProcessError(
                128, list(cmd), stderr="fatal: Authentication failed"
            )

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        with pytest.raises(subprocess.CalledProcessError):
            git_ls_remote("https://example.com/foo.git", "main")
        assert calls["n"] == 1

    def test_ls_remote_exhausts_attempts_then_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            raise subprocess.CalledProcessError(
                128, list(cmd), stderr="fatal: Connection timed out"
            )

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        with pytest.raises(subprocess.CalledProcessError):
            git_ls_remote("https://example.com/foo.git", "main")
        assert calls["n"] == 3  # default NSX_GIT_RETRIES

    def test_retries_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_GIT_RETRIES", "1")
        calls = {"n": 0}

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            raise subprocess.CalledProcessError(
                128, list(cmd), stderr="fatal: Connection reset by peer"
            )

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        with pytest.raises(subprocess.CalledProcessError):
            git_ls_remote("https://example.com/foo.git", "main")
        assert calls["n"] == 1

    def test_clone_retries_transient_and_resets_dest(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        dest = tmp_path / "clone"
        calls = {"n": 0}

        def fake_run(cmd, cwd=None, *, on_line=None, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if on_line is not None:
                on_line("Cloning into 'clone'...")
            if calls["n"] < 2:
                # Simulate a partially-populated dest left behind by the
                # aborted clone, then a transient transport error.
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "partial").write_text("x")
                if on_line is not None:
                    on_line("fatal: unable to access: Could not resolve host: x")
                raise subprocess.CalledProcessError(128, list(cmd))

        monkeypatch.setattr(subprocess_utils, "run", fake_run)

        git_clone("https://example.com/foo.git", dest, revision="main")
        assert calls["n"] == 2
        # ``before_retry`` must have cleared the stale partial clone.
        assert not (dest / "partial").exists()

    def test_backoff_is_capped_by_max_delay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # With a large base delay and many attempts, the exponential
        # growth must never exceed NSX_GIT_RETRY_MAX_DELAY.
        from neuralspotx.subprocess_utils import _git

        monkeypatch.setenv("NSX_GIT_RETRIES", "8")
        monkeypatch.setenv("NSX_GIT_RETRY_BASE_DELAY", "5")
        monkeypatch.setenv("NSX_GIT_RETRY_MAX_DELAY", "2")

        delays: list[float] = []
        monkeypatch.setattr(_git, "_sleep", delays.append)

        def fake_run_capture(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise subprocess.CalledProcessError(
                128, list(cmd), stderr="fatal: Connection timed out"
            )

        monkeypatch.setattr(subprocess_utils, "run_capture", fake_run_capture)

        with pytest.raises(subprocess.CalledProcessError):
            git_ls_remote("https://example.com/foo.git", "main")

        # 8 attempts -> 7 backoff sleeps, each clamped to the 2s cap.
        assert len(delays) == 7
        assert all(d <= 2.0 for d in delays)

    def test_empty_output_clone_is_retried(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # A streaming clone that fails with no captured output should
        # still be retried (treated as a transient blip).
        dest = tmp_path / "clone"
        calls = {"n": 0}

        def fake_run(cmd, cwd=None, *, on_line=None, **kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] < 2:
                raise subprocess.CalledProcessError(128, list(cmd))

        monkeypatch.setattr(subprocess_utils, "run", fake_run)

        git_clone("https://example.com/foo.git", dest, revision="main")
        assert calls["n"] == 2
