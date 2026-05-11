"""Phase 5 — git transport hardening.

Verifies that NSX refuses to operate on disallowed git transports
(``ext::``, ``file::``, ``file://``) and that every ``git`` invocation
carries the protocol allow-list ``-c`` overrides.
"""

from __future__ import annotations

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
