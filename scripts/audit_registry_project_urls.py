#!/usr/bin/env python3
"""Audit that every packaged registry project URL is reachable.

`src/neuralspotx/data/registry.lock.yaml` pins one git URL per project.
Nothing in the normal `nsx` resolution path (module add/sync/lock) touches a
project unless a module or starter-profile override actually resolves to it
(see `neuralspotx.registry_policy.orphaned_registry_project_report` for that
*structural* check, which is deterministic and runs as part of the normal
unit-test suite). But a project can be structurally reachable and still
point at a URL that no longer exists — e.g. a repo renamed, transferred, or
deleted upstream without the registry being updated.

This script performs the *network* half of that audit: for every project in
the packaged registry, run `git ls-remote` against its URL and report
success/failure. It is deliberately **not** part of `tests/` — network
calls in the normal pytest suite are flaky in CI and offline dev
environments, so this is a separately-invoked tool instead.

Run locally or in a scheduled/manual CI job:

    uv run python scripts/audit_registry_project_urls.py
    uv run python scripts/audit_registry_project_urls.py --json
    uv run python scripts/audit_registry_project_urls.py --project nsx-ambiq-sdk

Exit status is non-zero if any non-exempt project URL is unreachable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# `git ls-remote` against a deleted/renamed/private repo can otherwise block
# on an interactive username/password prompt — exactly the case this audit
# exists to detect. Force git to fail fast instead of hanging.
os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

from neuralspotx.constants import PACKAGED_PROJECT_NAME  # noqa: E402
from neuralspotx.metadata import load_registry_lock  # noqa: E402
from neuralspotx.subprocess_utils import git_ls_remote  # noqa: E402

# Projects exempt from the *reachability* requirement because they are
# resolved from packaged/self-referential content rather than a network
# clone in the normal built-in flow (see `project_config._is_packaged_module`
# / `PACKAGED_PROJECT_NAME`). Document the reason inline for every entry
# added here — this is the "packaged/self-reference exception" the registry
# hygiene audit is required to allow, not a general-purpose skip list.
PACKAGED_SELF_REFERENCE_EXCEPTIONS: frozenset[str] = frozenset({PACKAGED_PROJECT_NAME})


@dataclass(frozen=True, slots=True)
class ProjectUrlCheck:
    """Result of probing one packaged project's git URL."""

    project: str
    url: str | None
    revision: str | None
    reachable: bool | None  # None when skipped (no URL, or exempt)
    skipped_reason: str | None
    error: str | None


def _check_project(name: str, entry: dict[str, Any]) -> ProjectUrlCheck:
    url = entry.get("url")
    revision = entry.get("revision")

    if name in PACKAGED_SELF_REFERENCE_EXCEPTIONS:
        return ProjectUrlCheck(
            project=name,
            url=url,
            revision=revision,
            reachable=None,
            skipped_reason="packaged/self-reference exception",
            error=None,
        )

    if not isinstance(url, str) or not url:
        # Every packaged `projects` record is expected to carry a `url` (the
        # audit's whole point is confirming that url is live); a missing one
        # is a malformed registry entry, not something to silently pass over.
        return ProjectUrlCheck(
            project=name,
            url=url,
            revision=revision,
            reachable=False,
            skipped_reason=None,
            error="registry record has no 'url' to audit",
        )

    try:
        git_ls_remote(url)
    except Exception as exc:  # noqa: BLE001 - report every failure kind uniformly
        # `str(exc)` on a CalledProcessError is just "returned non-zero exit
        # status 128" — the useful diagnostic (e.g. "Repository not found",
        # an auth failure, or a DNS error) lives in the captured stderr.
        stderr = getattr(exc, "stderr", None)
        detail = stderr.strip() if isinstance(stderr, str) and stderr.strip() else str(exc)
        return ProjectUrlCheck(
            project=name,
            url=url,
            revision=revision,
            reachable=False,
            skipped_reason=None,
            error=detail,
        )
    return ProjectUrlCheck(
        project=name,
        url=url,
        revision=revision,
        reachable=True,
        skipped_reason=None,
        error=None,
    )


def audit_registry_project_urls(
    registry: dict[str, Any],
    *,
    only: str | None = None,
) -> list[ProjectUrlCheck]:
    """Probe every (or one) packaged project's git URL for reachability."""

    projects = registry.get("projects", {})
    names = sorted(projects) if only is None else [only]
    results = []
    for name in names:
        entry = projects.get(name)
        if not isinstance(entry, dict):
            raise SystemExit(f"unknown registry project: '{name}'")
        results.append(_check_project(name, entry))
    return results


def _print_report(results: list[ProjectUrlCheck]) -> int:
    failures = [r for r in results if r.reachable is False]
    for result in results:
        if result.reachable is True:
            status = "OK"
        elif result.reachable is False:
            status = "UNREACHABLE"
        else:
            status = f"SKIPPED ({result.skipped_reason})"
        print(f"{status:24s} {result.project}  {result.url or '<no url>'}")
        if result.error:
            print(f"    {result.error.strip().splitlines()[-1]}")
    print()
    print(f"{len(results)} project(s) checked, {len(failures)} unreachable.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default=None,
        help="Audit a single project name instead of every packaged project.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human-readable table.",
    )
    args = parser.parse_args(argv)

    registry = load_registry_lock(REPO_ROOT / "src" / "neuralspotx" / "data" / "registry.lock.yaml")
    results = audit_registry_project_urls(registry, only=args.project)

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
        return 1 if any(r.reachable is False for r in results) else 0

    return _print_report(results)


if __name__ == "__main__":
    raise SystemExit(main())
