"""Static guards for the CI-gated, immutable release workflow.

These tests parse `.github/workflows/release.yml` and assert on its
structure and embedded scripts rather than executing it, since the workflow
depends on live GitHub Actions context (PR metadata, branch pushes, workflow
dispatch) that is impractical to run locally. Keep assertions specific enough
that a regression in job wiring, permissions, or the pre-merge uv.lock sync
flow fails a test rather than silently reintroducing a release loop or a
stale-head race.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
DOC_PATH = Path(__file__).parents[1] / "docs" / "contributing" / "releases.md"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_workflow_text())


def _job_block_text(job_name: str) -> str:
    """Return this job's raw source slice (from its `  <job_name>:` header up
    to the next top-level `  <name>:` job header, or EOF).

    Unlike ``yaml.safe_dump(workflow["jobs"][job_name])``, this preserves the
    file's exact literal strings (quoting, line-wrapping) so substring
    assertions against the real script text stay meaningful and don't
    silently pass or fail due to YAML re-serialization.
    """
    text = _workflow_text()
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line == f"  {job_name}:\n")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace():
            continue
        if lines[i].startswith("  ") and not lines[i].startswith("   ") and lines[i].strip().endswith(":"):
            end = i
            break
    return "".join(lines[start:end])


def test_release_workflow_uses_full_action_shas_and_minimal_default_permissions() -> None:
    workflow = _workflow()

    assert workflow["permissions"] == {}
    assert workflow["jobs"]["release-please"]["permissions"] == {
        "contents": "write",
        "issues": "write",
        "pull-requests": "write",
    }
    assert workflow["jobs"]["sync-release-lock"]["permissions"] == {
        "contents": "write",
        "pull-requests": "read",
    }
    assert workflow["jobs"]["dispatch-release-pr-ci"]["permissions"] == {
        "actions": "write",
        "contents": "read",
    }

    for line in _workflow_text().splitlines():
        if "uses:" in line:
            action_ref = line.split("uses:", 1)[1].split("#", 1)[0].strip()
            assert "@" in action_ref
            assert len(action_ref.rsplit("@", 1)[1]) == 40


def test_release_publication_is_downstream_of_exact_commit_ci() -> None:
    workflow = _workflow()
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


# ---------------------------------------------------------------------------
# Pre-merge uv.lock sync on the release-please branch
# ---------------------------------------------------------------------------


def test_lock_sync_job_runs_between_release_please_and_ci_dispatch() -> None:
    """sync-release-lock must sit strictly between release-please and CI dispatch."""
    workflow = _workflow()
    jobs = workflow["jobs"]

    assert jobs["sync-release-lock"]["needs"] == "release-please"
    assert (
        jobs["sync-release-lock"]["if"]
        == "${{ needs.release-please.result == 'success' && needs.release-please.outputs.pr != '' }}"
    )
    assert jobs["dispatch-release-pr-ci"]["needs"] == "sync-release-lock"
    assert jobs["dispatch-release-pr-ci"]["if"] == "${{ needs.sync-release-lock.result == 'success' }}"

    # The dispatch job must not read the raw release-please PR output directly;
    # it only sees the lock-sync job's outputs.
    dispatch_text = yaml.safe_dump(jobs["dispatch-release-pr-ci"])
    assert "needs.release-please" not in dispatch_text
    assert "needs.sync-release-lock.outputs.branch" in dispatch_text
    assert "needs.sync-release-lock.outputs.head_sha" in dispatch_text


def test_lock_sync_uses_canonical_uv_lock_not_regex_mutation() -> None:
    text = _workflow_text()

    assert "\n          uv lock\n" in text
    # The old approach hand-edited the lockfile with a regex targeting the
    # editable package's version line; that pattern must be gone (changelog
    # heading parsing elsewhere in the file legitimately still uses re.compile).
    assert 'name = "neuralspotx"\\nversion = "' not in text
    assert "Could not locate editable neuralspotx package block in uv.lock" not in text


def test_lock_sync_dispatches_ci_against_the_final_synced_head() -> None:
    """CI must be dispatched against the post-sync commit, not the raw release-please head."""
    text = _workflow_text()
    workflow = _workflow()
    dispatch_steps = workflow["jobs"]["dispatch-release-pr-ci"]["steps"]

    step_names = [step["name"] for step in dispatch_steps]
    assert step_names.index("Confirm the branch still points at the synced head") < step_names.index(
        "Dispatch CI on the release-please PR branch"
    )

    assert 'remote_sha=$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/$BRANCH" --jq \'.object.sha\')' in text
    assert 'if [[ "$remote_sha" != "$EXPECTED_SHA" ]]; then' in text
    assert 'gh workflow run ci.yml --ref "$BRANCH" --repo "$GITHUB_REPOSITORY"' in text


def test_lock_sync_is_idempotent_when_lock_already_matches() -> None:
    text = _workflow_text()

    assert "if git diff --quiet -- uv.lock; then" in text
    assert 'echo "uv.lock already matches pyproject.toml; nothing to push."' in text
    assert "printf 'changed=false\\n' >> \"$GITHUB_OUTPUT\"" in text
    # On the no-op path the job must still report the original validated head
    # so CI dispatch has something to target.
    assert 'printf \'head_sha=%s\\n\' "$EXPECTED_SHA" >> "$GITHUB_OUTPUT"' in text


def test_lock_sync_commits_only_uv_lock() -> None:
    text = _workflow_text()

    assert "changed_files=$(git status --porcelain=v1 -- . | awk '{print $2}')" in text
    assert 'if [[ "$changed_files" != "uv.lock" ]]; then' in text
    assert "Refusing to push: expected only uv.lock to change" in text
    assert "git add uv.lock" in text
    # No wildcard `git add .`/`git add -A` that could sweep up unrelated files.
    assert "git add ." not in text
    assert "git add -A" not in text


def test_lock_sync_validates_the_release_branch_before_pushing() -> None:
    text = _workflow_text()

    assert 'package_name=$(jq -r \'.packages["."]["package-name"]\' release-please-config.json)' in text
    assert 'expected_branch="release-please--branches--main--components--${package_name}"' in text
    assert 'if [[ "$branch" != "$expected_branch" ]]; then' in text
    assert 'if [[ "$state" != "open" ]]; then' in text
    assert 'if [[ "$head_ref" != "$branch" ]]; then' in text
    assert (
        'if [[ "$head_repo" != "$GITHUB_REPOSITORY" || "$base_repo" != "$GITHUB_REPOSITORY" ]]; then' in text
    )
    assert "refusing to push" in text.lower()
    assert 'if [[ ! "$head_sha" =~ ^[0-9a-f]{40}$ ]]; then' in text

    # The subsequent checkout step re-verifies the fetched commit against the
    # already-validated head before any local branch is created from it.
    assert "actual_sha=$(git rev-parse FETCH_HEAD)" in text
    assert 'if [[ "$actual_sha" != "$EXPECTED_SHA" ]]; then' in text


def test_lock_sync_uses_bot_identity_and_plain_non_force_push() -> None:
    text = _workflow_text()

    assert 'git config user.name "github-actions[bot]"' in text
    assert 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in text
    assert 'git push origin "HEAD:refs/heads/$BRANCH"' in text
    assert "--force" not in text
    assert "-f " not in text
    assert "push --force" not in text
    # A "+" force-push refspec would bypass non-fast-forward protection
    # without tripping any of the checks above.
    assert "+HEAD" not in text
    assert '"+refs/heads/$BRANCH"' not in text


def test_lock_sync_has_a_branch_protection_fallback_that_re_validates_the_head() -> None:
    """If a direct push is blocked, the Contents API fallback must still be race-safe."""
    text = _workflow_text()
    sync_job_text = _job_block_text("sync-release-lock")

    assert "Direct push to $BRANCH was rejected (branch protection?)." in text
    assert 'gh api --method PUT "repos/${GITHUB_REPOSITORY}/contents/uv.lock"' in text
    # The fallback itself (inside sync-release-lock's push step) must
    # re-check the remote head before overwriting it via the API. Scoping
    # the count to this job's own raw source -- rather than the whole file
    # -- means this assertion can't pass by accident just because
    # dispatch-release-pr-ci has its own, separate copy of the same check.
    assert (
        sync_job_text.count(
            'remote_sha=$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/heads/$BRANCH" --jq \'.object.sha\')'
        )
        == 1
    )
    assert "aborting" in text.lower()


def test_lock_sync_push_step_has_gh_token_for_its_api_fallback() -> None:
    """The push step calls `gh api` in its fallback path and needs GH_TOKEN to do so."""
    workflow = _workflow()
    push_step = next(
        step
        for step in workflow["jobs"]["sync-release-lock"]["steps"]
        if step.get("id") == "push"
    )

    assert "gh api" in push_step["run"]
    assert push_step["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_every_gh_cli_step_declares_gh_token() -> None:
    """Any step invoking the `gh` CLI must have GH_TOKEN in its own step env.

    `gh` does not share actions/checkout's persisted git credentials; a step
    that runs `gh api`/`gh workflow run` without GH_TOKEN fails at runtime
    with an auth error, even though the workflow parses fine and other,
    string-matching tests could pass. This also has to catch indirect
    invocations, like the release-metadata step's
    ``subprocess.run(["gh", "api", ...])`` in embedded Python, not just the
    literal shell command forms -- a plain ``"gh api" in run`` substring
    check misses that (the tokens are separate list elements, not adjacent
    text), which would let a GH_TOKEN regression there go undetected.
    """
    workflow = _workflow()
    gh_invocation = re.compile(r'(?:\bgh\s+(?:api|workflow\s+run|pr)\b|(["\'])gh\1\s*,)')

    offenders = []
    for job_name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if not gh_invocation.search(run):
                continue
            env = step.get("env") or {}
            if "GH_TOKEN" not in env:
                offenders.append(f"{job_name} :: {step.get('name', step.get('id', '<unnamed>'))}")

    assert offenders == []


def test_post_release_lock_refresh_pr_jobs_are_removed() -> None:
    workflow = _workflow()
    text = _workflow_text()

    assert "refresh-uv-lock" not in workflow["jobs"]
    assert "dispatch-lock-refresh-ci" not in workflow["jobs"]
    assert "peter-evans/create-pull-request" not in text
    assert "automation/update-uv-lock" not in text


def test_publisher_still_uses_the_merged_release_landing_sha() -> None:
    """The release-context job must key off github.sha (the main push), not any PR branch."""
    workflow = _workflow()
    text = _workflow_text()

    release_context_steps = workflow["jobs"]["release-context"]["steps"]
    checkout_step = next(step for step in release_context_steps if step["name"] == "Checkout release target")
    assert checkout_step["with"]["ref"] == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.tag || github.sha }}"
    )
    assert 'target_sha="$LANDING_SHA"' in text
    assert "LANDING_SHA: ${{ github.sha }}" in text
    # release-context must not depend on the lock-sync branch at all.
    assert "sync-release-lock" not in yaml.safe_dump(workflow["jobs"]["release-context"])


def test_release_created_detection_is_merge_method_agnostic() -> None:
    """Release detection must not assume the release PR is a single commit.

    Once sync-release-lock can push a second (uv.lock) commit onto the
    release-please branch, diffing pyproject.toml between HEAD and HEAD^ on
    main stops being reliable for every GitHub merge method: a rebase merge
    (still enabled on this repository) would land both commits on `main`,
    making HEAD^ the version-bump commit and silently skipping the release.
    Detection must instead depend only on whether the release tag already
    exists, which holds regardless of merge method or commit count.
    """
    text = _workflow_text()

    assert 'git/ref/tags/{tag_name}' in text
    assert "tag_check.returncode == 0" in text
    assert 'git show HEAD^:pyproject.toml' not in text
    assert "parent_version" not in text
    assert "merge method" in text.lower()


def test_release_created_detection_fails_closed_on_non_404_tag_lookup_errors() -> None:
    """A tag-lookup failure that isn't a clean 404 must not be treated as "no tag".

    Otherwise an auth, rate-limit, or transient network failure on the `gh
    api` call would silently read as "this version hasn't been released
    yet" and try to re-publish an already-released version downstream.
    """
    workflow = _workflow()
    text = _workflow_text()

    assert '"HTTP 404" in tag_check.stderr' in text
    assert "Could not determine whether" in text
    assert "raise SystemExit" in text

    metadata_step = next(
        step
        for step in workflow["jobs"]["release-please"]["steps"]
        if step.get("id") == "release-metadata"
    )
    # `gh api`'s stderr is only inspectable if it's actually captured as text.
    assert "capture_output=True" in metadata_step["run"]
    assert "text=True" in metadata_step["run"]
    assert metadata_step["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_release_workflow_serializes_concurrent_runs() -> None:
    workflow = _workflow()

    concurrency = workflow["concurrency"]
    assert concurrency["group"] == "release"
    assert concurrency["cancel-in-progress"] is False
    # `queue: max` is required alongside `cancel-in-progress: false`: the
    # default `queue: single` cancels an already-*pending* run the instant a
    # second run queues behind it, which could silently drop a release
    # landing on main while exact-commit-ci is still polling for a prior run.
    assert concurrency["queue"] == "max"


def test_lock_sync_push_cannot_trigger_a_release_workflow_loop() -> None:
    """The uv.lock sync push must never retrigger release-please or this workflow."""
    workflow = _workflow()
    text = _workflow_text()

    # release.yml only reacts to pushes on main; pushing to the release-please
    # branch (a different ref) cannot re-invoke it, and GITHUB_TOKEN pushes
    # don't fire other workflows' `push`/`pull_request` triggers either way.
    # (PyYAML parses the bare `on:` mapping key as the boolean True.)
    assert workflow[True]["push"]["branches"] == ["main"]
    assert "GITHUB_TOKEN pushes do not trigger other" in text

    # No step re-runs release-please or opens another release PR after sync.
    sync_job_text = yaml.safe_dump(workflow["jobs"]["sync-release-lock"])
    assert "release-please-action" not in sync_job_text
    assert "create-pull-request" not in sync_job_text
