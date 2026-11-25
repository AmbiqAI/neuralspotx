"""Record which empty build directories NSX initialized for an app."""

from pathlib import Path

_MARKER = ".nsx-build-owner"


def mark_empty_build(app: Path, build: Path) -> None:
    build.mkdir(parents=True, exist_ok=True)
    if any(build.iterdir()):
        return
    try:
        with (build / _MARKER).open("x", encoding="utf-8") as marker:
            marker.write(str(app.resolve()))
    except FileExistsError:
        pass  # Another preparation of the same build initialized it first.


def initialized_by_app(app: Path, build: Path) -> bool:
    marker = build / _MARKER
    if marker.is_symlink() or not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8") == str(app.resolve())
    except (OSError, UnicodeError):
        return False
