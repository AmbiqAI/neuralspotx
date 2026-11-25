"""Cleanup ownership through the public app API."""

import shutil
from pathlib import Path

import pytest
import yaml

from neuralspotx import NSXError, clean_app, lock_app
from neuralspotx._build_ownership import mark_empty_build

BOARD = "apollo510_evb"


@pytest.fixture
def app(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    (root / "nsx.yml").write_text(
        yaml.safe_dump({
            "schema_version": 2,
            "project": {"name": "example"},
            "target": {"board": BOARD, "soc": "apollo510"},
            "baseline": "none",
            "modules": [{"name": "source", "source": {"vendored": True}}],
        })
    )
    source = root / "modules/source"
    source.mkdir(parents=True)
    (source / "app.c").write_text("int app;")
    return root


def build_tree(path: Path, app: Path, board: str = BOARD) -> None:
    mark_empty_build(app, path)
    (path / "CMakeCache.txt").write_text(
        f"CMAKE_HOME_DIRECTORY:INTERNAL={app}\n"
        f"CMAKE_CACHEFILE_DIR:INTERNAL={path}\nNSX_BOARD:STRING={board}\n"
    )


@pytest.mark.parametrize("with_receipt", [True, False])
def test_reset_preserves_authored_unowned_and_lock(app: Path, with_receipt: bool) -> None:
    if with_receipt:
        lock_app(app)
    source = app / "modules/source/app.c"
    unknown = app / "modules/new.c"
    unknown.write_text("unclassified")
    stale = app / "build_notes"
    stale.mkdir()
    other = app / "build/unrelated"
    build_tree(other, app.parent)
    owned = app / "build" / BOARD
    legacy = app / "build_armclang"
    build_tree(owned, app)
    build_tree(legacy, app)
    for _ in range(2):
        clean_app(app, reset=True, force=True)
        assert source.read_text() == "int app;"
        assert unknown.read_text() == "unclassified"
        assert other.exists() and stale.exists()
        assert not owned.exists() and not legacy.exists()
        assert (app / ".nsx/sync.lock").is_file()


def test_full_clean_ownership(app: Path, tmp_path: Path) -> None:
    external = tmp_path / "external"
    build_tree(external, app)
    clean_app(app, build_dir=external, full=True)
    assert not external.exists()
    for board, owner in [(BOARD, tmp_path), ("apollo510b_evb", app)]:
        build_tree(external, owner, board)
        with pytest.raises(NSXError, match="owned build"):
            clean_app(app, build_dir=external, full=True, force=True)
        assert external.is_dir()
    for unsafe in (app, app.parent, app / "modules/source"):
        with pytest.raises(NSXError, match="owned build"):
            clean_app(app, build_dir=unsafe, full=True)
        assert unsafe.exists()


def test_reset_without_app(tmp_path: Path) -> None:
    with pytest.raises(NSXError, match="nsx.yml"):
        clean_app(tmp_path, reset=True)
    assert not (tmp_path / ".nsx").exists()


def test_mixed_directory_and_legacy_cache_are_preserved(app: Path) -> None:
    build = app / "build_work"
    build.mkdir()
    source = build / "work.c"
    source.write_text("int keep;")
    build_tree(build, app)
    assert not (build / ".nsx-build-owner").exists()
    with pytest.raises(NSXError, match="owned build"):
        clean_app(app, full=True, build_dir=build)
    clean_app(app, reset=True, force=True)
    assert source.read_text() == "int keep;"


@pytest.mark.parametrize("reset", [True, False])
def test_clean_preserves_declared_source_inside_owned_build(app: Path, reset: bool) -> None:
    build = app / "build_work"
    build_tree(build, app)
    source = build / "authored"
    source.mkdir()
    (source / "source.c").write_text("int value;")
    manifest = app / "nsx.yml"
    cfg = yaml.safe_load(manifest.read_text())
    cfg["modules"].append({"name": "local", "source": {"path": "build_work/authored"}})
    manifest.write_text(yaml.safe_dump(cfg))
    if reset:
        clean_app(app, reset=True, force=True)
    else:
        with pytest.raises(NSXError, match="owned build"):
            clean_app(app, full=True, build_dir=build)
    assert (source / "source.c").exists()


def test_ambiguous_cache_preserved(app: Path) -> None:
    build = app / "build" / BOARD
    build_tree(build, app)
    with (build / "CMakeCache.txt").open("a") as stream:
        stream.write(f"CMAKE_HOME_DIRECTORY:INTERNAL={app.parent}\n")
    with pytest.raises(NSXError, match="owned build"):
        clean_app(app, full=True)
    assert build.exists()


def test_full_clean_relative_external_path(app: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build = app.parent / "out"
    build_tree(build, app)
    monkeypatch.chdir(app)
    clean_app(".", full=True, build_dir="../out")
    assert not build.exists()


def test_copied_marker_does_not_adopt_mixed_directory(app: Path) -> None:
    owned, mixed = app / "build_original", app / "build_analysis"
    build_tree(owned, app)
    mixed.mkdir()
    source = mixed / "authored.c"
    source.write_text("int keep;")
    shutil.copy(owned / ".nsx-build-owner", mixed)
    build_tree(mixed, app)
    clean_app(app, reset=True)
    assert source.exists()
    assert not owned.exists()


def test_full_clean_normalizes_before_removal(app: Path) -> None:
    build = app / "build" / BOARD
    build_tree(build, app)
    (build / "nsx").mkdir()
    clean_app(app, full=True, build_dir=build / "nsx/..")
    assert not build.exists()


@pytest.mark.parametrize("origin", ["shorthand", "registry", "inline", "workspace"])
def test_declared_source_link_inside_owned_build(app: Path, tmp_path: Path, origin: str) -> None:
    build = app / "build" / BOARD
    build_tree(build, app)
    source = tmp_path / "local"
    source.mkdir()
    alias = build / "source_alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    manifest = app / "nsx.yml"
    cfg = yaml.safe_load(manifest.read_text())
    relative = alias.relative_to(app).as_posix()
    if origin == "shorthand":
        cfg["modules"].append({"name": "local", "source": {"path": relative}})
    elif origin == "workspace":
        overlays = app / "overlays"
        overlays.mkdir()
        (overlays / "registry.yml").write_text(
            yaml.safe_dump({"projects": {"local": {"local_path": "../" + relative}}})
        )
        cfg["registry"] = {"layers": [{"workspace": "overlays/registry.yml"}]}
    else:
        layer = {"projects": {"local": {"local_path": relative}}}
        if origin == "registry":
            cfg["module_registry"] = layer
        else:
            cfg["registry"] = {"layers": [{"inline": layer}]}
    manifest.write_text(yaml.safe_dump(cfg))
    clean_app(app, reset=True)
    assert alias.is_symlink()


@pytest.mark.parametrize("reset", [True, False])
def test_checkout_in_build_preserved_without_receipt(app: Path, reset: bool) -> None:
    build = app / "build_example"
    build_tree(build, app)
    driver = build / "driver"
    driver.mkdir()
    (driver / "source.c").write_text("int offline;")
    manifest = app / "nsx.yml"
    cfg = yaml.safe_load(manifest.read_text())
    cfg["module_registry"] = {
        "projects": {
            "driver": {"url": "https://example.invalid/driver", "path": "build_example/driver"}
        }
    }
    manifest.write_text(yaml.safe_dump(cfg))
    if reset:
        clean_app(app, reset=True)
    else:
        with pytest.raises(NSXError, match="owned build"):
            clean_app(app, full=True, build_dir=build)
    assert (driver / "source.c").exists()


@pytest.mark.parametrize("reset", [True, False])
def test_cached_sdk_override_protects_app_builds(app: Path, reset: bool) -> None:
    owner, work = app / "build_owner", app / "build_work"
    build_tree(owner, app)
    build_tree(work, app)
    sdk = work / "sdk"
    sdk.mkdir()
    source = sdk / "hal.c"
    source.write_bytes(b"int sdk;")
    with (owner / "CMakeCache.txt").open("a", encoding="utf-8") as cache:
        cache.write(f"NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH={sdk}\n")
    for _ in range(2):
        if reset:
            clean_app(app, reset=True, force=True)
        else:
            for target in (owner, work):
                with pytest.raises(NSXError, match="owned build"):
                    clean_app(app, full=True, build_dir=target)
        assert source.read_bytes() == b"int sdk;" and owner.is_dir()


def test_full_clean_external_build_with_separate_sdk_override(app: Path, tmp_path: Path) -> None:
    build = tmp_path / "external-build"
    build_tree(build, app)
    sdk = tmp_path / "external-sdk"
    sdk.mkdir()
    with (build / "CMakeCache.txt").open("a", encoding="utf-8") as cache:
        cache.write(f"NSX_AMBIQSUITE_ROOT_OVERRIDE:PATH={sdk}\n")
    clean_app(app, full=True, build_dir=build)
    assert sdk.is_dir() and not build.exists()
