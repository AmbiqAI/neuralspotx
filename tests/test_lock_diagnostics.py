"""No-network coverage of lock diagnostics and their logging contract."""

from __future__ import annotations

import logging

import pytest

from neuralspotx._logging import _level_for
from neuralspotx.nsx_lock import LockKind, NsxLock, ResolvedModule
from neuralspotx.operations._lock_diagnostics import warn_unpinned_git_constraints


@pytest.fixture(autouse=True)
def warning_level(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="neuralspotx")


def _entry(ref: str, kind: LockKind = LockKind.GIT, tag: str | None = None) -> ResolvedModule:
    return ResolvedModule(
        project="demo",
        kind=kind,
        constraint=ref,
        tag=tag,
        acquired_at="2026-01-01T00:00:00Z",
        vendored_at="modules/demo",
        content_hash="sha256:" + "a" * 64,
        url="https://secret@example.com/demo.git",
        commit="a" * 40,
    )


@pytest.mark.parametrize(
    ("ref", "tag", "warns"),
    [
        ("main", None, True),
        ("deadbee", None, True),
        ("a" * 40, None, False),
        ("v1.0", "v1.0", False),
        ("deadbee", "deadbee", False),
        ("refs/tags/v1.0", None, True),
    ],
)
def test_ref_diagnostics(
    ref: str, tag: str | None, warns: bool, caplog: pytest.LogCaptureFixture
) -> None:
    lock = NsxLock(target={"board": "board-a"}, modules={"mod": _entry(ref, tag=tag)})
    with caplog.at_level(logging.WARNING, logger="neuralspotx"):
        warn_unpinned_git_constraints(lock)
    assert bool(caplog.records) is warns
    if warns:
        assert "Unpinned Git constraint" in caplog.text
        assert "board-a" in caplog.text and ref in caplog.text
        assert "module_registry.projects.demo.revision" in caplog.text
        assert "secret" not in caplog.text and "https://" not in caplog.text


@pytest.mark.parametrize(
    "kind", [LockKind.PACKAGED, LockKind.LOCAL, LockKind.VENDORED, LockKind.UNRESOLVED]
)
def test_non_git_rows_are_excluded(kind: LockKind, caplog: pytest.LogCaptureFixture) -> None:
    entry = _entry("main", kind)
    entry.project = "neuralspotx"
    entry.commit = None
    warn_unpinned_git_constraints(NsxLock(modules={"mod": entry}))
    assert not caplog.records


def test_grouping_is_deterministic_and_source_sensitive(caplog: pytest.LogCaptureFixture) -> None:
    other = _entry("main")
    other.url = "https://other-secret@example.com/demo.git"
    lock = NsxLock(
        target={"board": "board-b"},
        modules={"z": _entry("main"), "a": _entry("main"), "other": other},
    )
    warn_unpinned_git_constraints(lock)
    assert len(caplog.records) == 2
    assert any("modules [a, z]" in r.message for r in caplog.records)
    assert all("board-b" in r.message for r in caplog.records)
    assert "secret" not in caplog.text


def test_git_project_name_is_not_exempt_and_quiet_uses_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entry = _entry("main")
    entry.project = "neuralspotx"
    lock = NsxLock(modules={"mod": entry})
    warn_unpinned_git_constraints(lock)
    assert len(caplog.records) == 1
    caplog.clear()
    with caplog.at_level(_level_for(0, quiet=True), logger="neuralspotx"):
        warn_unpinned_git_constraints(lock)
    assert not caplog.records
