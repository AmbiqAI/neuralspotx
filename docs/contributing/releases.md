# Releases

NSX uses Release Please to manage version bumps and changelog entries for the
Python package. The release workflow creates the published tag only after
fresh CI has passed for the exact release landing commit.

## Release Flow

Releases are automated through the `release.yml` workflow. As a contributor you
take **two actions** — everything else runs in CI:

1. **Merge your change to `main`.** Release Please opens or updates a *release
   PR* that accumulates the version bump and changelog. The workflow then
   regenerates `uv.lock` on that release PR branch itself (see
   [uv.lock Sync](#uvlock-sync)) and dispatches CI for it.
2. **Merge the release PR.** That triggers exact-commit CI. After it succeeds,
   the workflow creates an immutable annotated tag, then publishes the GitHub
   release assets and package to PyPI.

```mermaid
gitGraph
    commit id: "feature"
    branch release-please
    commit id: "version + changelog"
    commit id: "uv.lock sync" type: HIGHLIGHT
    checkout main
    merge release-please
    commit id: "exact landing-commit CI"
    tag: "neuralspotx-v0.6.3" (annotated)
```

The workflow verifies that the new tag peels to the exact release landing
commit that passed CI. It then builds and checks the Python distributions,
smoke-tests the installed wheel, attaches the artifacts and a matching
`SHA256SUMS` manifest to the GitHub release, and publishes the packages to
PyPI. There is no follow-up PR: `uv.lock` is already in sync by the time the
release PR merges (see [uv.lock Sync](#uvlock-sync)).

## Version Source of Truth

The package version in `pyproject.toml` is the version source of truth for the
Python package at release time.

For new releases, the release workflow validates that:

- the release tag is exactly `neuralspotx-v<version>`
- the tag version exactly matches `pyproject.toml`
- the tag is annotated and its peeled target is the CI-reviewed release
  landing commit

The published `neuralspotx-v0.7.9` tag is the final documented lightweight-tag
exception. Existing historical tags remain available and are never moved,
deleted, or replaced.

Example:

- `pyproject.toml`: `0.2.0`
- release tag: `neuralspotx-v0.2.0`

If those do not match, the release build fails.

## Manual Rebuilds

`release.yml` also supports `workflow_dispatch` with an optional `tag` input.
Leaving `tag` empty intentionally runs only Release Please release-PR
generation/update; it does not publish a release. Publication occurs after the
release PR is merged and the resulting `main` push passes exact-commit CI.

This is intended only for rebuilding an existing tagged release, for example
when:

- artifact upload failed
- the workflow logic changed and you need to regenerate release artifacts

This manual path does not create a new version, move a tag, or create a release
PR. It first runs fresh CI on the existing tag's peeled commit, then rebuilds
artifacts for an existing release tag such as `neuralspotx-v0.6.3` or the
legacy form `v0.6.3`. PyPI uses `skip-existing` for this retry-only path so a
successful prior upload does not make an asset retry fail on duplicates.

## PyPI Publishing

PyPI publishing runs in the same `release.yml` workflow as Release Please, the
artifact build, and the GitHub release asset upload.

This is intentional. PyPI trusted publishing must stay in the same workflow
file as the release job, because PyPI does not support delegating the publish
step to a reusable workflow.

The publish job uses GitHub OIDC trusted publishing against the repository's
configured PyPI project. It runs when Release Please creates a root release in
that workflow, or when a manual rebuild targets an existing release tag.

Before either GitHub or PyPI receives an artifact, the release workflow:

1. runs fresh CI for the exact release commit
2. runs `twine check` against both the wheel and source distribution
3. installs the wheel into an isolated environment
4. creates an app without network bootstrap
5. creates and validates a module scaffold

These checks exercise packaged templates from the installed distribution. A
command working from a source checkout is not sufficient evidence that its
templates or other data files were included in the wheel.

## uv.lock Sync

Historically, `uv.lock` drifted out of sync with `pyproject.toml` for one
release cycle: Release Please bumped the version on `main`, but `uv.lock`
(which embeds the editable `neuralspotx` package's own version) was only
refreshed by a second, post-release PR against `automation/update-uv-lock`.
That meant every release briefly landed on `main` with a stale lockfile, and
required a human to notice and merge the follow-up PR.

The workflow now closes that gap **before** the release PR merges. After
Release Please creates or updates its release PR, the `sync-release-lock` job:

1. validates that the reported PR is this repository's own open,
   `release-please--branches--main--components--neuralspotx` branch (never a
   fork or an unrelated PR) and resolves its exact head commit via the GitHub
   API,
2. checks out that exact commit and runs `uv lock` — the canonical
   dependency-resolution command, not a hand-rolled regex edit — so the
   editable package version and any other lock metadata stay coherent,
3. commits and pushes **only** `uv.lock` back to that same branch with the
   `github-actions[bot]` identity, using a plain, non-force push, if and only
   if the lockfile actually changed. If `uv.lock` was already in sync (for
   example, on a second Release Please update to the same PR), the job is a
   no-op.

Because this push uses the job's `GITHUB_TOKEN` rather than a personal access
token, it does not itself trigger another workflow run — the same reason the
release PR's initial creation doesn't. The `dispatch-release-pr-ci` job runs
immediately afterward, re-confirms the branch still points at the commit the
sync job just produced (or confirmed unchanged), and only then dispatches CI
for it. This guarantees the release PR's required status check always
reflects the final, lock-synced commit, never the pre-sync Release Please
commit, and it removes the old per-release `refresh-uv-lock` /
`dispatch-lock-refresh-ci` jobs and their `automation/update-uv-lock` PR
entirely — there is nothing left to review or merge after the fact.

If a direct push to the release branch is ever rejected (for example, by
branch protection), the job falls back to committing the single `uv.lock`
file through the GitHub Contents API instead, after re-confirming the branch
has not moved since it was validated. Either way, there is still only one
release PR: Release Please's own.

The whole workflow (Release Please, the lock sync, and any manual rebuild)
also runs under a single `concurrency` group with `queue: max`, so overlapping
triggers queue up (FIFO) instead of racing each other on the same release
branch or tag. `queue: max` matters as much as `cancel-in-progress: false`
here: the default `queue: single` behavior cancels an already-*pending* run
the moment a second run queues behind it — which would have been able to
silently drop a release landing on `main` while `exact-commit-ci` was still
polling for a prior run.

Because the release PR can now carry a second commit (the lock sync, on top
of Release Please's version bump), whether a given push to `main` actually
lands a *new* release is derived from tag existence — does
`neuralspotx-v<version>` already exist? — rather than by diffing
`pyproject.toml` between `HEAD` and its parent commit. That check is
independent of how many commits the merged release PR contains or which
GitHub merge method (merge commit, squash, or rebase) is used to land it.

## Contributor Guidance

- Do not create ad hoc release tags outside the Release Please flow.
- Do not move or delete a published release tag; a reused tag fails closed.
- Do not hand-edit version numbers unless you are intentionally repairing the
  release metadata.
- Do not hand-edit `uv.lock`'s editable `neuralspotx` version line either;
  the `sync-release-lock` job keeps it current on the release PR branch by
  running `uv lock`.
- If a tagged release needs to be retried, use the manual rebuild path for the
  existing tag.
- Keep release notes and changelog generation owned by Release Please.
- Treat distribution smoke-test failures as packaging regressions; do not
  bypass the check or publish the affected artifact manually.
