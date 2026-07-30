"""Static guards for the CI-gated, immutable release workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
DOC_PATH = Path(__file__).parents[1] / "docs" / "contributing" / "releases.md"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_release_workflow_uses_full_action_shas_and_minimal_default_permissions() -> None:
    workflow = yaml.safe_load(_workflow_text())

    assert workflow["permissions"] == {}
    assert workflow["jobs"]["release-please"]["permissions"] == {
        "contents": "write",
        "issues": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["dispatch-release-pr-ci"]["permissions"] == {
        "actions": "write",
        "contents": "read",
    }
    assert workflow["jobs"]["refresh-uv-lock"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }

    for line in _workflow_text().splitlines():
        if "uses:" in line:
            action_ref = line.split("uses:", 1)[1].split("#", 1)[0].strip()
            assert "@" in action_ref
            assert len(action_ref.rsplit("@", 1)[1]) == 40


def test_release_publication_is_downstream_of_exact_commit_ci() -> None:
    workflow = yaml.safe_load(_workflow_text())
    text = _workflow_text()
    release_step = next(
        step for step in workflow["jobs"]["release-please"]["steps"] if step.get("id") == "release"
    )

    assert release_step["with"]["skip-github-release"] is True
    assert "release-metadata" in text
    assert "exact-commit-ci" in workflow["jobs"]["build"]["needs"]
    assert "exact-commit-ci" in workflow["jobs"]["github-release"]["needs"]
    assert "exact-commit-ci" in workflow["jobs"]["pypi-publish"]["needs"]
    assert 'ref="refs/heads/$CI_BRANCH"' in text
    assert 'gh workflow run ci.yml --ref "$CI_BRANCH"' in text
    assert 'gh api --method DELETE "repos/${GITHUB_REPOSITORY}/git/refs/heads/$CI_BRANCH"' in text
    assert "No fresh CI run appeared for exact commit" in text
    assert 'required_jobs=$(printf \'%s\' "$jobs" |' in text
    assert 'needs.exact-commit-ci.result == \'success\'' in text
    assert "skip-existing: ${{ github.event_name == 'workflow_dispatch' && inputs.tag != '' }}" in text


def test_new_tags_are_annotated_and_fail_closed() -> None:
    text = _workflow_text()

    assert "git/tags" in text
    assert "git/refs" in text
    assert "--field \"type=commit\"" in text
    assert "peeled_sha" in text
    assert "Creating a ref, rather than force-updating one" in text
    assert "git push origin :" not in text
    assert "git tag -d" not in text
    assert "SHA256SUMS" in text


def test_release_documentation_describes_the_legacy_exception() -> None:
    docs = DOC_PATH.read_text(encoding="utf-8")

    assert "annotated" in docs
    assert "peeled" in docs
    assert "neuralspotx-v0.7.9" in docs
    assert "lightweight-tag\nexception" in docs
