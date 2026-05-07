"""Tests for the small ``_parallel`` helper used by lock/outdated.

The helper is intentionally minimal: a thread-pool ``map`` that
preserves order, a serial fast path under ``NSX_RESOLVE_PARALLELISM=1``,
and an env-var override.  These tests pin those contracts.
"""

from __future__ import annotations

import threading
import time

import pytest

from neuralspotx._parallel import parallel_map, resolve_workers


class TestResolveWorkers:
    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NSX_RESOLVE_PARALLELISM", raising=False)
        assert resolve_workers(default=4) == 4

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_RESOLVE_PARALLELISM", "3")
        assert resolve_workers(default=8) == 3

    def test_env_one_forces_serial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_RESOLVE_PARALLELISM", "1")
        assert resolve_workers() == 1

    def test_invalid_env_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_RESOLVE_PARALLELISM", "not-a-number")
        assert resolve_workers(default=4) == 4

    def test_floor_is_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NSX_RESOLVE_PARALLELISM", "0")
        assert resolve_workers() == 1
        monkeypatch.setenv("NSX_RESOLVE_PARALLELISM", "-5")
        assert resolve_workers() == 1


class TestParallelMap:
    def test_empty_input(self) -> None:
        assert parallel_map(lambda x: x * 2, []) == []

    def test_preserves_order(self) -> None:
        # Reverse-sorted sleeps so the first item finishes last; the
        # result list must still be [0, 1, ..., 9].
        def slow(i: int) -> int:
            time.sleep(0.01 * (10 - i))
            return i

        out = parallel_map(slow, list(range(10)), max_workers=4)
        assert out == list(range(10))

    def test_actually_parallel(self) -> None:
        # Four 100ms sleeps must complete in < 250ms with 4 workers.
        # Serial would be ~400ms.
        barrier = threading.Barrier(4)

        def wait(_: int) -> None:
            barrier.wait(timeout=2.0)
            time.sleep(0.05)

        t0 = time.monotonic()
        parallel_map(wait, list(range(4)), max_workers=4)
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5, f"parallel_map did not parallelise (took {elapsed:.2f}s)"

    def test_serial_fast_path_when_workers_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Under workers=1 the helper must not spin up a thread; verify
        # by asserting the function runs on the calling thread.
        main_thread = threading.get_ident()
        seen: list[int] = []

        def record(x: int) -> int:
            seen.append(threading.get_ident())
            return x

        out = parallel_map(record, [1, 2, 3], max_workers=1)
        assert out == [1, 2, 3]
        assert all(tid == main_thread for tid in seen)

    def test_first_exception_propagates(self) -> None:
        def fail(i: int) -> int:
            if i == 2:
                raise RuntimeError("boom")
            return i

        with pytest.raises(RuntimeError, match="boom"):
            parallel_map(fail, list(range(5)), max_workers=2)
