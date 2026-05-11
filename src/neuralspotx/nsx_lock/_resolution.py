"""Git remote ref/commit resolution for ``nsx lock``."""

from __future__ import annotations

import subprocess

from .._errors import NSXGitError
from ..subprocess_utils import git_ls_remote


def resolve_commit(url: str, ref: str) -> str:
    """Resolve *ref* (branch/tag/SHA) on remote *url* to a 40-char SHA.

    Uses ``git ls-remote`` so no clone is needed. If *ref* already looks
    like a full 40-char SHA, it is returned as-is. For annotated tags,
    the **peeled** commit (``refs/tags/<x>^{}``) is preferred over the
    tag-object SHA, so the recorded commit is what ``git checkout <tag>``
    would actually land on. Raises :class:`ResolutionError` if the
    remote is unreachable or the ref is not found.
    """

    if _looks_like_full_sha(ref):
        return ref.lower()

    sha, _matched = resolve_ref(url, ref)
    return sha


def resolve_ref(url: str, ref: str, *, bypass_cache: bool = False) -> tuple[str, str | None]:
    """Resolve *ref* and report what kind of upstream ref it matched.

    Returns ``(sha, matched_kind)`` where ``matched_kind`` is one of
    ``"tag"``, ``"branch"``, ``"sha"`` or ``None``. ``sha`` is always
    the underlying commit SHA (annotated tags are peeled).

    Results are cached on-disk for ``NSX_RESOLVE_TTL`` seconds (default
    300).  Set ``bypass_cache=True`` (e.g. ``nsx lock --update``) to
    force a fresh ``git ls-remote``.
    """

    if _looks_like_full_sha(ref):
        return ref.lower(), "sha"

    if not bypass_cache:
        from .. import _resolve_cache

        cached = _resolve_cache.get(url, ref)
        if cached is not None:
            return cached

    result = _resolve_ref(url, ref)

    from .. import _resolve_cache

    _resolve_cache.put(url, ref, result[0], result[1])
    return result


def _resolve_ref(url: str, ref: str) -> tuple[str, str | None]:
    # Pass both `<ref>` and `<ref>^{}` so annotated tags return both
    # the tag-object line and the peeled-commit line. Branches and
    # lightweight tags only return one line; the `^{}` query is a no-op.
    # Routes through the hardened git_ls_remote helper so the registry
    # URL is validated and the protocol allow-list is applied (parity
    # with git_clone / git_clone_at_commit).
    try:
        result = git_ls_remote(url, ref, f"{ref}^{{}}")
    except NSXGitError as exc:
        raise ResolutionError(str(exc)) from exc
    except subprocess.CalledProcessError as exc:
        raise ResolutionError(
            f"git ls-remote failed for {url} @ {ref}: exit {exc.returncode}"
        ) from exc

    tag_sha: str | None = None
    peeled_sha: str | None = None
    branch_sha: str | None = None
    other_sha: str | None = None

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, name = line.partition("\t")
        sha = sha.strip()
        if not sha:
            continue
        if name == f"refs/tags/{ref}^{{}}":
            peeled_sha = sha
        elif name == f"refs/tags/{ref}":
            tag_sha = sha
        elif name == f"refs/heads/{ref}":
            branch_sha = sha
        elif name == ref and other_sha is None:
            other_sha = sha

    if peeled_sha:
        # Annotated tag: peeled commit is what `git checkout <tag>` lands on.
        return peeled_sha, "tag"
    if tag_sha:
        # Lightweight tag (no separate tag object): tag SHA *is* the commit.
        return tag_sha, "tag"
    if branch_sha:
        return branch_sha, "branch"
    if other_sha:
        return other_sha, None
    raise ResolutionError(f"Unable to resolve revision '{ref}' on {url}")


class ResolutionError(RuntimeError):
    """Raised when a git remote cannot be resolved during ``nsx lock``."""


def _looks_like_full_sha(s: str) -> bool:
    return len(s) == 40 and all(c in "0123456789abcdefABCDEF" for c in s)
