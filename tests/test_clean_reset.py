"""Cleanup ownership through the public app API."""

from pathlib import Path

import pytest
import yaml

from neuralspotx import NSXError, clean_app, lock_app

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
    path.mkdir(parents=True, exist_ok=True)
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
