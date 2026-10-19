# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Shared test fixtures."""

from __future__ import annotations

import threading

import pytest

from neuralspotx.subprocess_utils import _git, _runner


@pytest.fixture(autouse=True)
def fresh_shutdown_flag(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Give every test its own subprocess shutdown flag.

    An interrupted ``cli.main`` calls ``terminate_live_children()``, which
    sets a process-wide flag so no new child starts while ``nsx`` exits. A
    real ``nsx`` process exits right after; a test does not, so the flag
    must not leak into the tests that run after it.
    """

    flag = threading.Event()
    monkeypatch.setattr(_runner, "_SHUTTING_DOWN", flag)
    monkeypatch.setattr(_git, "_SHUTTING_DOWN", flag)
    return flag
