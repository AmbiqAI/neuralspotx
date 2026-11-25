"""Read generated CMake configuration without running a build."""

import re
from pathlib import Path

from .._errors import NSXConfigError


def _cmake_cache_value(build_dir: Path, variable: str) -> str | None:
    """Return one typed CMake cache value without invoking CMake."""

    cache_file = build_dir / "CMakeCache.txt"
    try:
        lines = cache_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    prefix = f"{variable}:"
    for cache_line in lines:
        if cache_line.startswith(prefix) and "=" in cache_line:
            return cache_line.split("=", 1)[1]
    return None


def read_owned_cache(app: Path, build: Path) -> dict[str, str]:
    """Read one complete cache and verify the owning source and binary directories."""
    cache = build / "CMakeCache.txt"
    try:
        lines = cache.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise NSXConfigError(f"Unreadable CMake cache; use a fresh build directory: {exc}") from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith(("#", "//")):
            continue
        match = re.fullmatch(r'(?:"([^"]+)"|([^:=]+)):([A-Z_]+)=(.*)', line)
        if match is None:
            raise NSXConfigError("Malformed CMake cache; use a fresh build directory.")
        key = match.group(1) or match.group(2)
        if key in values:
            raise NSXConfigError(f"Duplicate CMake cache key {key}; use a fresh build directory.")
        values[key] = match.group(4)
    source = values.get("CMAKE_HOME_DIRECTORY")
    owner = values.get("CMAKE_CACHEFILE_DIR")
    if (
        not source
        or not Path(source).is_absolute()
        or Path(source).resolve() != app
        or not owner
        or not Path(owner).is_absolute()
        or Path(owner).resolve() != build
    ):
        raise NSXConfigError(
            "CMake cache belongs to another app/build or is invalid; use a fresh build directory."
        )
    return values
