"""Tiny ThreadPoolExecutor wrapper for nsx's I/O-bound fan-out work.

The lock/outdated paths spend most of their wall-clock time in
``git ls-remote`` (one process per module) and ``git clone``-and-hash
(one process per unique ``(url, commit)`` pair).  Both are network/IO
bound, so a small thread pool gives a near-linear speedup for apps
with many git-hosted modules without changing semantics.

Public API:

* :func:`resolve_workers` \u2014 honour the ``NSX_RESOLVE_PARALLELISM``
  env var with a sensible default and floor.
* :func:`parallel_map` \u2014 order-preserving thread-pool ``map`` that
  surfaces the first exception (additional exceptions are suppressed
  to avoid noisy duplicate tracebacks).

Both are intentionally tiny so callers can keep their existing serial
control flow and just substitute the inner I/O loop.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

_DEFAULT_WORKERS = 8
_ENV_VAR = "NSX_RESOLVE_PARALLELISM"


def resolve_workers(default: int = _DEFAULT_WORKERS) -> int:
    """Return the effective worker count, honouring ``NSX_RESOLVE_PARALLELISM``.

    Setting the env var to ``"1"`` forces serial execution \u2014 useful for
    debugging or for environments that misbehave under concurrent
    ``git`` invocations.  Invalid values fall back to *default*.
    """

    raw = os.environ.get(_ENV_VAR)
    if raw is None or not raw.strip():
        return max(1, default)
    try:
        n = int(raw)
    except ValueError:
        return max(1, default)
    return max(1, n)


def parallel_map(
    fn: Callable[[T], R],
    items: Iterable[T],
    *,
    max_workers: int | None = None,
) -> list[R]:
    """Apply *fn* to each of *items* concurrently, preserving order.

    Returns results in the same order as *items*.  When *max_workers*
    is ``None`` the value from :func:`resolve_workers` is used; the
    pool is sized down to ``len(items)`` when smaller, so calling with
    a single item incurs no thread overhead.

    Exceptions raised by *fn* propagate \u2014 the first one wins.  The
    pool is shut down (with ``cancel_futures=True``) before re-raising
    so in-flight work cannot leak past the call site.
    """

    materialised = list(items)
    if not materialised:
        return []
    workers = max_workers if max_workers is not None else resolve_workers()
    workers = max(1, min(workers, len(materialised)))
    if workers == 1:
        # Serial fast-path \u2014 no thread, no executor overhead, identical
        # exception semantics.
        return [fn(item) for item in materialised]

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nsx-resolve") as ex:
        try:
            return list(ex.map(fn, materialised))
        except BaseException:
            # Cancel anything still queued so we don't keep the
            # interpreter alive past the failure.
            ex.shutdown(wait=False, cancel_futures=True)
            raise
