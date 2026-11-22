"""Exercise the actual post-link actions using a tiny native CMake project."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

CMAKE_DIR = Path(__file__).resolve().parents[1] / "src/neuralspotx/cmake"


@pytest.mark.parametrize(
    ("family", "section_size", "expect_binary"),
    [
        ("corstone300", None, True),
        ("corstone310", 0, True),
        ("corstone310", 4, False),
        ("corstone320", None, False),
    ],
)
def test_corstone_post_link_binary(tmp_path, family, section_size, expect_binary):
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is required")
    (tmp_path / "main.c").write_text("int main(void) { return 0; }\n")
    # A native tool stands in for size/objcopy so the test also runs without
    # GNU cross tools on macOS and Windows. Its output is GNU size -A format.
    (tmp_path / "tool.c").write_text(
        r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc == 3 && strcmp(argv[1], "-A") == 0) {
        const char *size = getenv("CORSTONE_TEST_SECTION_SIZE");
        puts(".text 128 0");
        if (size && *size) printf(".npu_model   %s   1879048192\n", size);
    } else if (argc == 4 && strcmp(argv[1], "-Obinary") == 0) {
        FILE *out = fopen(argv[3], "wb");
        if (!out) return 1;
        fputs("compact", out);
        return fclose(out) != 0;
    }
    return 0;
}
"""
    )
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\nproject(check C)\n"
        f'include("{CMAKE_DIR.as_posix()}/nsx_app_bootstrap.cmake")\n'
        'set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/out/$<0:>")\n'
        "add_executable(tool tool.c)\nadd_executable(app main.c)\nadd_dependencies(app tool)\n"
        'set(CMAKE_SIZE "$<TARGET_FILE:tool>")\nset(CMAKE_OBJCOPY "$<TARGET_FILE:tool>")\n'
        f'set(NSX_SDK_PROVIDER corstone)\nset(NSX_SOC_FAMILY "{family}")\nnsx_finalize_app(app)\n'
    )
    build = tmp_path / "build"
    subprocess.run([cmake, "-S", str(tmp_path), "-B", str(build)], check=True)
    binary = build / "out" / "app.bin"
    binary.parent.mkdir(exist_ok=True)
    binary.write_bytes(b"old image")
    env = dict(
        os.environ, CORSTONE_TEST_SECTION_SIZE="" if section_size is None else str(section_size)
    )
    subprocess.run([cmake, "--build", str(build), "--config", "Release"], check=True, env=env)
    if expect_binary:
        assert binary.read_bytes() == b"compact"
    else:
        assert not binary.exists()
