"""Unit tests for scripts/audit_registry_project_urls.py's pure logic.

All network calls (`git_ls_remote`) are monkeypatched — this exercises the
audit's classification logic (OK / UNREACHABLE / SKIPPED) deterministically,
consistent with keeping the *actual* network probe out of the normal
pytest suite (see `scripts/audit_registry_project_urls.py`'s module
docstring and `docs/architecture/metadata-model.md`).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_registry_project_urls.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("audit_registry_project_urls", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def audit_module() -> ModuleType:
    return _load_script_module()


def test_packaged_self_reference_is_skipped_not_probed(
    audit_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail_if_called(url: str) -> None:  # pragma: no cover - should never run
        raise AssertionError(f"git_ls_remote should not be called for a skip, got url={url!r}")

    monkeypatch.setattr(audit_module, "git_ls_remote", _fail_if_called)

    result = audit_module._check_project(
        audit_module.PACKAGED_PROJECT_NAME,
        {"url": "https://github.com/AmbiqAI/neuralspotx.git", "revision": "main"},
    )

    assert result.reachable is None
    assert result.skipped_reason == "packaged/self-reference exception"
    assert result.error is None


def test_missing_url_is_a_failure_not_a_skip(audit_module: ModuleType) -> None:
    """A packaged project with no `url` is malformed, not exempt.

    Regression test for a review finding: this case used to be reported as
    SKIPPED (`reachable=None`), which let a malformed registry entry pass
    the audit with exit code 0. It must be reported as unreachable.
    """

    result = audit_module._check_project("broken-project", {"revision": "v1"})

    assert result.reachable is False
    assert result.skipped_reason is None
    assert result.error


def test_reachable_url_reports_ok(
    audit_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_module, "git_ls_remote", lambda url: None)

    result = audit_module._check_project(
        "some-project", {"url": "https://example.invalid/some-project.git", "revision": "v1"}
    )

    assert result.reachable is True
    assert result.error is None


def test_unreachable_url_surfaces_git_stderr(
    audit_module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_not_found(url: str) -> None:
        raise subprocess.CalledProcessError(
            128,
            ["git", "ls-remote", url],
            output="",
            stderr="ERROR: Repository not found.\nfatal: Could not read from remote repository.\n",
        )

    monkeypatch.setattr(audit_module, "git_ls_remote", _raise_not_found)

    result = audit_module._check_project(
        "gone-project", {"url": "https://github.com/AmbiqAI/gone-project.git", "revision": "v1"}
    )

    assert result.reachable is False
    assert result.error is not None
    assert "Repository not found" in result.error


def test_audit_registry_project_urls_rejects_unknown_project(audit_module: ModuleType) -> None:
    registry = {"projects": {"known": {"url": "https://example.invalid/known.git"}}}

    with pytest.raises(SystemExit):
        audit_module.audit_registry_project_urls(registry, only="does-not-exist")


def test_print_report_exit_code_reflects_failures(
    audit_module: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    results = [
        audit_module.ProjectUrlCheck(
            project="ok-project",
            url="https://example.invalid/ok.git",
            revision="v1",
            reachable=True,
            skipped_reason=None,
            error=None,
        ),
        audit_module.ProjectUrlCheck(
            project="bad-project",
            url="https://example.invalid/bad.git",
            revision="v1",
            reachable=False,
            skipped_reason=None,
            error="Repository not found.",
        ),
    ]

    exit_code = audit_module._print_report(results)

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "UNREACHABLE" in out
    assert "bad-project" in out
