"""``--frozen`` on a fresh checkout: missing fetchable modules (#289).

Apps keep fetched modules out of git, so a fresh clone has an empty
``modules/``. ``--frozen`` must fetch those at the locked revision and
verify them strictly, while still refusing to touch a module that is
present but differs from the lock.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXIntegrityError, NSXModuleError, module_registry
from neuralspotx.nsx_lock import (
    NSX_TOOLING_AUTOGEN_FILES,
    LockKind,
    NsxLock,
    ResolvedModule,
    hash_manifest,
    hash_tree,
    write_lock,
)
from neuralspotx.operations import _sync, sync_app_impl
from neuralspotx.operations._sync import (
    _is_absent,
    _sync_fetchable_entry,
    _sync_local_board_overlay,
    _sync_local_entry,
    _SyncContext,
    _verify_packaged_cmake_tree,
)
from neuralspotx.project_config import _copy_packaged_tree

_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _write_tree(dest: Path, content: str) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "src.c").write_text(content, encoding="utf-8")


def _locked_hash(tmp_path: Path, content: str) -> str:
    reference = tmp_path / "reference"
    _write_tree(reference, content)
    return hash_tree(reference)


def _entry(content_hash: str, *, commit: str | None = _COMMIT) -> ResolvedModule:
    return ResolvedModule(
        project="demo-proj",
        kind=LockKind.GIT,
        constraint="v1.0.0",
        vendored_at="modules/demo-proj",
        content_hash=content_hash,
        acquired_at="2026-10-18T00:00:00+00:00",
        url="https://example.com/demo.git",
        commit=commit,
    )


def _ctx(app_dir: Path, *, frozen: bool) -> _SyncContext:
    return _SyncContext(
        app_dir=app_dir,
        registry={},
        cmake_nsx=app_dir / "cmake" / "nsx",
        frozen=frozen,
        force=False,
    )


def _fake_vendor(monkeypatch: pytest.MonkeyPatch, vendored_dir: Path, content: str) -> list[str]:
    """Replace the git fetch with one that writes ``content`` at the vendored path."""

    calls: list[str] = []

    def _vendor(app_dir: Path, name: str, registry: dict[str, Any], commit: str, **_: Any) -> None:  # noqa: ARG001
        calls.append(commit)
        _write_tree(vendored_dir, content)

    monkeypatch.setattr(module_registry, "_vendor_git_module_at_commit", _vendor)
    return calls


def test_frozen_fetches_missing_module_at_locked_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")
    vendored_paths: set[Path] = set()

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, vendored_paths
    )

    assert changed == 1
    assert calls == [_COMMIT]
    assert hash_tree(vendored_dir) == entry.content_hash
    assert vendored_dir in vendored_paths


def test_frozen_removes_fetched_module_that_does_not_match_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    _fake_vendor(monkeypatch, vendored_dir, "upstream moved")

    with pytest.raises(NSXIntegrityError, match="fetched at its locked revision") as excinfo:
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert excinfo.value.module == "demo-mod"
    assert not vendored_dir.exists()


def test_frozen_refuses_present_module_that_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    _write_tree(vendored_dir, "hand patched")
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    with pytest.raises(NSXIntegrityError, match="does not match nsx.lock") as excinfo:
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert excinfo.value.module == "demo-mod"
    assert calls == []
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "hand patched"


def test_frozen_refuses_missing_git_module_without_locked_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"), commit=None)
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    with pytest.raises(NSXIntegrityError, match="records no commit"):
        _sync_fetchable_entry(_ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set())

    assert calls == []
    assert not vendored_dir.exists()


def test_unfrozen_keeps_mismatched_fetch_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: without --frozen a drifted upstream is kept with a warning."""

    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))
    _fake_vendor(monkeypatch, vendored_dir, "upstream moved")
    # Record the warning directly: the nsx logger's propagation depends on
    # which CLI tests ran earlier in the session, so caplog is not reliable.
    warnings: list[str] = []
    monkeypatch.setattr(_sync._log, "warning", lambda msg, *args: warnings.append(msg % args))

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=False), "demo-mod", entry, vendored_dir, set()
    )

    assert changed == 1
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "upstream moved"
    assert any("has drifted since lock" in w for w in warnings)


def _cmake_lock(content_hash: str) -> NsxLock:
    return NsxLock(
        modules={
            "nsx-cmake": ResolvedModule(
                project="neuralspotx",
                kind=LockKind.PACKAGED,
                constraint="packaged",
                vendored_at="cmake/nsx",
                content_hash=content_hash,
                acquired_at="2026-10-18T00:00:00+00:00",
                tool_version="0.0.0",
            )
        }
    )


def _cmake_hash(tmp_path: Path, content: str) -> str:
    reference = tmp_path / "cmake-reference"
    _write_tree(reference, content)
    return hash_tree(reference, exclude_names=NSX_TOOLING_AUTOGEN_FILES)


def test_frozen_removes_created_cmake_tree_that_does_not_match_then_retry_restores(
    tmp_path: Path,
) -> None:
    app_dir = tmp_path / "app"
    cmake_nsx = app_dir / "cmake" / "nsx"
    lock = _cmake_lock(_cmake_hash(tmp_path, "locked tool"))

    # Sync created cmake/nsx from a different neuralspotx version.
    _write_tree(cmake_nsx, "other tool")
    with pytest.raises(NSXIntegrityError, match="ships different content"):
        _verify_packaged_cmake_tree(app_dir, lock, cmake_nsx, frozen=True, created=True)
    assert not cmake_nsx.exists()

    # A retry with the matching neuralspotx version restores and passes.
    _write_tree(cmake_nsx, "locked tool")
    _verify_packaged_cmake_tree(app_dir, lock, cmake_nsx, frozen=True, created=True)
    assert cmake_nsx.exists()


def test_frozen_keeps_preexisting_cmake_tree_that_does_not_match(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    cmake_nsx = app_dir / "cmake" / "nsx"
    lock = _cmake_lock(_cmake_hash(tmp_path, "locked tool"))
    _write_tree(cmake_nsx, "other tool")

    with pytest.raises(NSXIntegrityError, match="ships different content"):
        _verify_packaged_cmake_tree(app_dir, lock, cmake_nsx, frozen=True, created=False)
    assert cmake_nsx.exists()


def test_unfrozen_cmake_tree_mismatch_only_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    cmake_nsx = app_dir / "cmake" / "nsx"
    lock = _cmake_lock(_cmake_hash(tmp_path, "locked tool"))
    _write_tree(cmake_nsx, "other tool")
    warnings: list[str] = []
    monkeypatch.setattr(_sync._log, "warning", lambda msg, *args: warnings.append(msg % args))

    _verify_packaged_cmake_tree(app_dir, lock, cmake_nsx, frozen=False, created=True)

    assert cmake_nsx.exists()
    assert any("has drifted since lock" in w for w in warnings)


def _fake_packaged_vendor(
    monkeypatch: pytest.MonkeyPatch, vendored_dir: Path, content: str
) -> list[str]:
    calls: list[str] = []

    def _vendor(app_dir: Path, name: str, registry: dict[str, Any]) -> None:  # noqa: ARG001
        calls.append(name)
        _write_tree(vendored_dir, content)

    monkeypatch.setattr(module_registry, "_vendor_packaged_module_into_app", _vendor)
    return calls


def _packaged_entry(content_hash: str) -> ResolvedModule:
    return ResolvedModule(
        project="neuralspotx",
        kind=LockKind.PACKAGED,
        constraint="packaged",
        vendored_at="boards/demo_evb",
        content_hash=content_hash,
        acquired_at="2026-10-18T00:00:00+00:00",
        tool_version="0.0.0",
    )


@pytest.mark.parametrize("frozen", [True, False])
def test_interrupted_fetch_of_missing_module_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen: bool
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"))

    def _interrupted(
        app_dir: Path, name: str, registry: dict[str, Any], commit: str, **_: Any
    ) -> None:  # noqa: ARG001
        (vendored_dir / ".git").mkdir(parents=True)
        raise KeyboardInterrupt

    monkeypatch.setattr(module_registry, "_vendor_git_module_at_commit", _interrupted)
    with pytest.raises(KeyboardInterrupt):
        _sync_fetchable_entry(_ctx(app_dir, frozen=frozen), "demo-mod", entry, vendored_dir, set())
    assert not vendored_dir.exists()

    # The next run fetches again instead of reporting local changes.
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")
    _sync_fetchable_entry(_ctx(app_dir, frozen=frozen), "demo-mod", entry, vendored_dir, set())
    assert calls == [_COMMIT]


def test_failed_refetch_keeps_a_module_that_was_already_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    _write_tree(vendored_dir, "older content")
    entry = _entry(_locked_hash(tmp_path, "locked"))

    def _fails(*_: Any, **__: Any) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(module_registry, "_vendor_git_module_at_commit", _fails)
    with pytest.raises(RuntimeError):
        _sync_fetchable_entry(_ctx(app_dir, frozen=False), "demo-mod", entry, vendored_dir, set())
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "older content"


def test_frozen_fetches_missing_packaged_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "boards" / "demo_evb"
    entry = _packaged_entry(_locked_hash(tmp_path, "packaged"))
    calls = _fake_packaged_vendor(monkeypatch, vendored_dir, "packaged")

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=True), "nsx-board-demo", entry, vendored_dir, set()
    )

    assert changed == 1
    assert calls == ["nsx-board-demo"]


def test_frozen_rejects_missing_packaged_module_from_another_tool_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "boards" / "demo_evb"
    entry = _packaged_entry(_locked_hash(tmp_path, "packaged"))
    _fake_packaged_vendor(monkeypatch, vendored_dir, "another version")

    with pytest.raises(NSXIntegrityError, match="fetched at its locked revision"):
        _sync_fetchable_entry(
            _ctx(app_dir, frozen=True), "nsx-board-demo", entry, vendored_dir, set()
        )
    assert not vendored_dir.exists()


def test_frozen_refuses_edited_packaged_module_and_points_at_nsx_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "boards" / "demo_evb"
    _write_tree(vendored_dir, "edited board")
    entry = _packaged_entry(_locked_hash(tmp_path, "packaged"))
    calls = _fake_packaged_vendor(monkeypatch, vendored_dir, "packaged")

    with pytest.raises(NSXIntegrityError, match="run `nsx lock` after an upgrade"):
        _sync_fetchable_entry(
            _ctx(app_dir, frozen=True), "nsx-board-demo", entry, vendored_dir, set()
        )
    assert calls == []
    assert (vendored_dir / "src.c").read_text(encoding="utf-8") == "edited board"


def test_frozen_with_force_leaves_a_matching_module_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    _write_tree(vendored_dir, "locked")
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")
    ctx = _SyncContext(
        app_dir=app_dir,
        registry={},
        cmake_nsx=app_dir / "cmake" / "nsx",
        frozen=True,
        force=True,
    )

    assert _sync_fetchable_entry(ctx, "demo-mod", entry, vendored_dir, set()) == 0
    assert calls == []


@pytest.mark.parametrize("commit", ["--upload-pack=touch x", "deadbeef", "0" * 39, "G" * 40])
def test_invalid_locked_commit_is_refused_before_git_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, commit: str
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    entry = _entry(_locked_hash(tmp_path, "locked"), commit=commit)
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    with pytest.raises(NSXIntegrityError, match="invalid commit"):
        _sync_fetchable_entry(_ctx(app_dir, frozen=False), "demo-mod", entry, vendored_dir, set())
    assert calls == []


def test_frozen_treats_an_empty_module_dir_as_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_dir = tmp_path / "app"
    vendored_dir = app_dir / "modules" / "demo-proj"
    vendored_dir.mkdir(parents=True)
    entry = _entry(_locked_hash(tmp_path, "locked"))
    calls = _fake_vendor(monkeypatch, vendored_dir, "locked")

    changed = _sync_fetchable_entry(
        _ctx(app_dir, frozen=True), "demo-mod", entry, vendored_dir, set()
    )

    assert changed == 1
    assert calls == [_COMMIT]


def _local_setup(tmp_path: Path) -> tuple[Path, Path, ResolvedModule, _SyncContext]:
    app_dir = tmp_path / "app"
    source = tmp_path / "src-local"
    _write_tree(source, "local source")
    mirror = app_dir / "modules" / "demo-local"
    entry = ResolvedModule(
        project="demo-local",
        kind=LockKind.LOCAL,
        constraint="local",
        vendored_at="modules/demo-local",
        content_hash=hash_tree(source),
        acquired_at="2026-10-18T00:00:00+00:00",
    )
    ctx = _SyncContext(
        app_dir=app_dir,
        registry={
            "projects": {"demo-local": {"local_path": str(source), "path": "modules/demo-local"}}
        },
        cmake_nsx=app_dir / "cmake" / "nsx",
        frozen=True,
        force=False,
    )
    return source, mirror, entry, ctx


def test_frozen_creates_a_missing_local_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, mirror, entry, ctx = _local_setup(tmp_path)
    calls: list[str] = []

    def _mirror(app_dir: Path, name: str, registry: dict[str, Any]) -> None:  # noqa: ARG001
        calls.append(name)
        _write_tree(mirror, (source / "src.c").read_text(encoding="utf-8"))

    monkeypatch.setattr(module_registry, "_vendor_local_module_into_app", _mirror)

    assert _sync_local_entry(ctx, "demo-local", entry, mirror, set()) == 1
    assert calls == ["demo-local"]


def test_frozen_refuses_a_local_mirror_that_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, mirror, entry, ctx = _local_setup(tmp_path)
    _write_tree(mirror, "edited mirror")
    calls: list[str] = []
    monkeypatch.setattr(
        module_registry,
        "_vendor_local_module_into_app",
        lambda app_dir, name, registry: calls.append(name),  # noqa: ARG005
    )

    with pytest.raises(NSXModuleError, match="Refusing under --frozen"):
        _sync_local_entry(ctx, "demo-local", entry, mirror, set())
    assert calls == []


def test_frozen_with_force_leaves_a_matching_local_mirror_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, mirror, entry, ctx = _local_setup(tmp_path)
    _write_tree(mirror, (source / "src.c").read_text(encoding="utf-8"))
    ctx = _SyncContext(
        app_dir=ctx.app_dir,
        registry=ctx.registry,
        cmake_nsx=ctx.cmake_nsx,
        frozen=True,
        force=True,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        module_registry,
        "_vendor_local_module_into_app",
        lambda app_dir, name, registry: calls.append(name),  # noqa: ARG005
    )

    assert _sync_local_entry(ctx, "demo-local", entry, mirror, set()) == 0
    assert calls == []


def _overlay_ctx(tmp_path: Path) -> tuple[_SyncContext, Path, Path]:
    app_dir = tmp_path / "app"
    source = tmp_path / "board-src"
    _write_tree(source / "boards" / "demo_evb", "board files")
    ctx = _SyncContext(
        app_dir=app_dir,
        registry={
            "modules": {
                "nsx-board-demo": {
                    "project": "demo-boards",
                    "revision": "local",
                    "metadata": "boards/demo_evb/nsx-module.yaml",
                }
            }
        },
        cmake_nsx=app_dir / "cmake" / "nsx",
        frozen=True,
        force=False,
    )
    return ctx, source, app_dir / "boards" / "demo_evb"


def test_frozen_creates_a_missing_local_board_overlay(tmp_path: Path) -> None:
    ctx, source, destination = _overlay_ctx(tmp_path)

    assert _sync_local_board_overlay(ctx, "nsx-board-demo", source, None) == 1
    assert hash_tree(destination) == hash_tree(source / "boards" / "demo_evb")


def test_frozen_refuses_a_local_board_overlay_that_differs(tmp_path: Path) -> None:
    ctx, source, destination = _overlay_ctx(tmp_path)
    _write_tree(destination, "edited board")

    with pytest.raises(NSXIntegrityError, match="Refusing under --frozen"):
        _sync_local_board_overlay(ctx, "nsx-board-demo", source, None)
    assert (destination / "src.c").read_text(encoding="utf-8") == "edited board"


def test_is_absent_treats_missing_and_empty_directories_alike(tmp_path: Path) -> None:
    assert _is_absent(tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    assert _is_absent(tmp_path / "empty")
    _write_tree(tmp_path / "full", "x")
    assert not _is_absent(tmp_path / "full")


def test_frozen_creates_an_empty_local_board_overlay(tmp_path: Path) -> None:
    ctx, source, destination = _overlay_ctx(tmp_path)
    destination.mkdir(parents=True)

    assert _sync_local_board_overlay(ctx, "nsx-board-demo", source, None) == 1
    assert hash_tree(destination) == hash_tree(source / "boards" / "demo_evb")


def test_interrupted_board_overlay_copy_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, source, destination = _overlay_ctx(tmp_path)
    real_copytree = _sync.shutil.copytree

    def _interrupted(src: Path, dst: Path, **_: Any) -> None:  # noqa: ARG001
        Path(dst).mkdir(parents=True, exist_ok=True)
        (Path(dst) / "partial.c").write_text("half", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(_sync.shutil, "copytree", _interrupted)
    with pytest.raises(OSError):
        _sync_local_board_overlay(ctx, "nsx-board-demo", source, None)
    assert not destination.exists()

    monkeypatch.setattr(_sync.shutil, "copytree", real_copytree)
    assert _sync_local_board_overlay(ctx, "nsx-board-demo", source, None) == 1


def test_interrupted_local_mirror_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, mirror, entry, ctx = _local_setup(tmp_path)

    def _interrupted(app_dir: Path, name: str, registry: dict[str, Any]) -> None:  # noqa: ARG001
        _write_tree(mirror, "half")
        raise KeyboardInterrupt

    monkeypatch.setattr(module_registry, "_vendor_local_module_into_app", _interrupted)
    with pytest.raises(KeyboardInterrupt):
        _sync_local_entry(ctx, "demo-local", entry, mirror, set())
    assert not mirror.exists()


def _packaged_cmake_hash(tmp_path: Path) -> str:
    reference = tmp_path / "cmake-packaged"
    _copy_packaged_tree("neuralspotx", "cmake", reference)
    return hash_tree(reference, exclude_names=NSX_TOOLING_AUTOGEN_FILES)


def _write_offline_app(tmp_path: Path, tooling_hash: str) -> Path:
    """An app whose lock needs no network: a vendored module and cmake/nsx."""

    app_dir = tmp_path / "app"
    _write_tree(app_dir / "modules" / "modA", "vendored")
    cfg = {
        "schema_version": 2,
        "project": {"name": "offline"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "modules": [{"name": "modA", "source": {"vendored": True}}],
    }
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    acquired = "2026-10-18T00:00:00+00:00"
    lock = NsxLock(
        manifest_hash=hash_manifest(app_dir / "nsx.yml"),
        target={"board": "apollo510_evb", "soc": "apollo510", "toolchain": "arm-none-eabi-gcc"},
        modules={
            "nsx-tooling": ResolvedModule(
                project="neuralspotx",
                kind=LockKind.PACKAGED,
                constraint="packaged",
                vendored_at="cmake/nsx",
                content_hash=tooling_hash,
                acquired_at=acquired,
                tool_version="0.0.0",
            ),
            "modA": ResolvedModule(
                project="modA",
                kind=LockKind.VENDORED,
                constraint="vendored",
                vendored_at="modules/modA",
                content_hash=hash_tree(app_dir / "modules" / "modA"),
                acquired_at=acquired,
            ),
        },
    )
    write_lock(app_dir, lock)
    return app_dir


def test_frozen_sync_removes_cmake_tree_it_filled_into_an_empty_dir_then_retry_passes(
    tmp_path: Path,
) -> None:
    """Sync level: an empty cmake/nsx counts as created, so a rejected fill is removed."""

    app_dir = _write_offline_app(tmp_path, tooling_hash="sha256:" + "0" * 64)
    cmake_nsx = app_dir / "cmake" / "nsx"
    cmake_nsx.mkdir(parents=True)

    with pytest.raises(NSXIntegrityError, match="ships different content"):
        sync_app_impl(app_dir, frozen=True)
    assert not cmake_nsx.exists()

    # Re-record the lock for the installed neuralspotx; the retry restores cmake/nsx.
    app_dir = _write_offline_app(tmp_path, tooling_hash=_packaged_cmake_hash(tmp_path))
    sync_app_impl(app_dir, frozen=True)
    assert hash_tree(cmake_nsx, exclude_names=NSX_TOOLING_AUTOGEN_FILES) == _packaged_cmake_hash(
        tmp_path
    )


def test_frozen_sync_keeps_a_verified_cmake_tree_when_another_tool_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sync level: --frozen does not overwrite a cmake/nsx that matches the lock."""

    reference = tmp_path / "locked-tooling"
    _write_tree(reference, "tooling the lock recorded")
    app_dir = _write_offline_app(
        tmp_path, tooling_hash=hash_tree(reference, exclude_names=NSX_TOOLING_AUTOGEN_FILES)
    )
    cmake_nsx = app_dir / "cmake" / "nsx"
    _write_tree(cmake_nsx, "tooling the lock recorded")

    def _other_tool(package: str, resource: str, dest: Path) -> None:  # noqa: ARG001
        _write_tree(dest, "tooling from another neuralspotx")

    monkeypatch.setattr(_sync, "_copy_packaged_tree", _other_tool)

    sync_app_impl(app_dir, frozen=True)

    assert (cmake_nsx / "src.c").read_text(encoding="utf-8") == "tooling the lock recorded"


def test_frozen_sync_interrupted_cmake_refresh_leaves_nothing_then_retry_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sync level: a fresh checkout's interrupted cmake/nsx copy is removed."""

    app_dir = _write_offline_app(tmp_path, tooling_hash=_packaged_cmake_hash(tmp_path))
    cmake_nsx = app_dir / "cmake" / "nsx"
    real_copy = _sync._copy_packaged_tree

    def _interrupted(package: str, resource: str, dest: Path) -> None:  # noqa: ARG001
        _write_tree(dest, "half")
        raise KeyboardInterrupt

    monkeypatch.setattr(_sync, "_copy_packaged_tree", _interrupted)
    with pytest.raises(KeyboardInterrupt):
        sync_app_impl(app_dir, frozen=True)
    assert not cmake_nsx.exists()

    monkeypatch.setattr(_sync, "_copy_packaged_tree", real_copy)
    sync_app_impl(app_dir, frozen=True)
    assert hash_tree(cmake_nsx, exclude_names=NSX_TOOLING_AUTOGEN_FILES) == _packaged_cmake_hash(
        tmp_path
    )
