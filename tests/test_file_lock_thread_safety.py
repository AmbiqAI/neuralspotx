"""Regression tests for the M3 remediation item: thread-safety of
``file_lock`` internal state.

Two issues motivated this fix:

1. ``_held_paths`` was a plain ``set`` mutated from inside the
   reentrancy fast-path.  Two threads racing on ``app_lock(same_dir)``
   could both observe the key as "already held" and skip the OS-level
   acquire entirely, so the critical section ran concurrently.  The
   fix migrates ``_held_paths`` to a ``contextvars.ContextVar`` holding
   a ``frozenset`` so each thread / asyncio task has its own view.

2. ``_warned`` was a plain ``set`` mutated under print, with no guard.
   Concurrent fail-open warnings could race the membership check and
   double-print or interleave the message.  The fix wraps the check +
   insert in a ``threading.Lock``.
"""

from __future__ import annotations

import threading
from pathlib import Path

from neuralspotx import file_lock


def test_held_paths_is_per_context(tmp_path: Path) -> None:
    """Two threads racing on the same app dir must serialise.

    If reentrancy were process-global (the old bug), the second thread
    would hit the fast-path and run *concurrently* with the first.
    With the per-context ContextVar each thread acquires the OS-level
    lock and the body is fully serialised.
    """
    app = tmp_path / "app"
    app.mkdir()

    enter_count = 0
    max_concurrent = 0
    state_lock = threading.Lock()
    in_section = 0
    barrier = threading.Barrier(2)

    def worker() -> None:
        nonlocal enter_count, max_concurrent, in_section
        barrier.wait()  # maximise the race
        with file_lock.app_lock(app):
            with state_lock:
                in_section += 1
                enter_count += 1
                if in_section > max_concurrent:
                    max_concurrent = in_section
            # Hold the lock briefly so an overlap would be observable.
            for _ in range(100):
                pass
            with state_lock:
                in_section -= 1

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert enter_count == 2, "both threads should have entered exactly once"
    assert max_concurrent == 1, (
        f"app_lock body ran with {max_concurrent} concurrent holders; thread-safety regression."
    )


def test_held_paths_default_is_frozenset() -> None:
    """Drift guard: the ContextVar must hold an immutable frozenset so
    callers can't accidentally mutate one context's view from another."""
    held = file_lock._held_paths.get()
    assert isinstance(held, frozenset)


def test_app_lock_is_still_reentrant_within_a_thread(tmp_path: Path) -> None:
    """Per-context tracking must NOT break the documented intra-thread
    reentrancy (outer ``nsx update`` calls ``nsx lock`` then ``nsx sync``)."""
    app = tmp_path / "app"
    app.mkdir()
    with file_lock.app_lock(app):
        # Nested call in same thread/context must be a no-op, not deadlock.
        with file_lock.app_lock(app):
            pass


def test_warn_once_is_thread_safe(monkeypatch, capsys) -> None:
    """``_warn_once`` must emit each unique message exactly once even
    when many threads race on it concurrently."""
    file_lock._warned.clear()

    msg = "race-condition-test-message"
    n_threads = 32
    barrier = threading.Barrier(n_threads)

    def worker() -> None:
        barrier.wait()
        file_lock._warn_once(msg)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    captured = capsys.readouterr()
    occurrences = captured.err.count(msg)
    assert occurrences == 1, (
        f"_warn_once printed message {occurrences} times under contention; expected exactly 1."
    )
    file_lock._warned.clear()
