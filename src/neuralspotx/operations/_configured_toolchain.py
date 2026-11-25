"""Verify explicit NSX selections against the toolchain CMake actually loaded."""

import re
from dataclasses import dataclass
from pathlib import Path

from .._errors import NSXToolchainError
from ..constants import SUPPORTED_TOOLCHAINS, Toolchain
from ._cmake_cache import read_owned_cache


@dataclass(frozen=True)
class _Driver:
    cache_key: str
    program: str
    cmake_id: str


# The three NSX toolchain files select these drivers with find_program.
_ARMCLANG = _Driver("ARMCLANG", "armclang", "armclang")
_ATFE_CLANG = _Driver("ATFE_CLANG", "clang", "clang")
_DRIVERS = {
    Toolchain.GCC: {
        "C": _Driver("ARM_NONE_EABI_GCC", "arm-none-eabi-gcc", "gnu"),
        "CXX": _Driver("ARM_NONE_EABI_GXX", "arm-none-eabi-g++", "gnu"),
        "ASM": _Driver("ARM_NONE_EABI_AS", "arm-none-eabi-gcc", "gnu"),
    },
    Toolchain.ARMCLANG: dict.fromkeys(("C", "CXX", "ASM"), _ARMCLANG),
    Toolchain.ATFE: {
        "C": _ATFE_CLANG,
        "CXX": _Driver("ATFE_CLANGXX", "clang++", "clang"),
        "ASM": _ATFE_CLANG,
    },
}


def selected_toolchain(value: str) -> Toolchain:
    try:
        return Toolchain.parse(value)
    except ValueError as exc:
        raise NSXToolchainError(str(exc)) from exc


def verify_configured_toolchain(
    app: Path, build: Path, requested: str | None, cache: dict[str, str] | None = None
) -> None:
    if requested is None:
        return
    toolchain = selected_toolchain(requested)
    app, build = app.resolve(), build.resolve()
    if cache is None:
        cache = read_owned_cache(app, build)

    def mismatch(observed: str) -> NSXToolchainError:
        return NSXToolchainError(
            f"Requested toolchain '{toolchain}', but {build} records {observed}. "
            "Use a fresh --build-dir for the requested toolchain."
        )

    version = ".".join(
        cache.get(f"CMAKE_CACHE_{key}_VERSION", "") for key in ("MAJOR", "MINOR", "PATCH")
    )
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise mismatch("an unknown CMake writer version")
    records = build / "CMakeFiles" / version
    # CMAKE_TOOLCHAIN_FILE in the cache can be overwritten by a later -D
    # without changing the toolchain in CMake's generated system record.
    try:
        system = (records / "CMakeSystem.cmake").read_text(encoding="utf-8")
        includes = re.findall(r'^include\("([^"\n]+)"\)$', system, re.MULTILINE)
        expected = app / "cmake" / "nsx" / "toolchains" / SUPPORTED_TOOLCHAINS[toolchain]
        if len(includes) != 1 or Path(includes[0]).resolve() != expected.resolve():
            observed = ", ".join(includes) or "no toolchain file"
            raise mismatch(observed)

        for language, expected_driver in _DRIVERS[toolchain].items():
            record = records / f"CMake{language}Compiler.cmake"
            if not record.exists():
                continue  # CMake only writes compiler records for enabled languages.
            content = record.read_text(encoding="utf-8")
            prefix = f"CMAKE_{language}_COMPILER"
            driver = re.findall(rf'^set\({prefix} "([^"\n]+)"\)$', content, re.MULTILINE)
            family = re.findall(rf'^set\({prefix}_ID "([^"\n]+)"\)$', content, re.MULTILINE)
            if (
                len(driver) != 1
                or len(family) != 1
                or family[0].lower() != expected_driver.cmake_id
                or Path(driver[0]).name.lower().removesuffix(".exe") != expected_driver.program
                or not cache.get(expected_driver.cache_key)
                or Path(driver[0]).resolve() != Path(cache[expected_driver.cache_key]).resolve()
            ):
                executable = ", ".join(driver) or "unknown executable"
                detected = ", ".join(family) or "unknown ID"
                raise mismatch(f"{language} compiler {executable} ({detected})")
    except (OSError, UnicodeError) as exc:
        raise mismatch(f"unreadable CMake toolchain information ({exc})") from exc
