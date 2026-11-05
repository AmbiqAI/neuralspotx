"""Read generated CMake configuration without running a build."""

from pathlib import Path


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
