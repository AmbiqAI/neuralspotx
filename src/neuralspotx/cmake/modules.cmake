# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# Stable entry point for existing generated apps. Module state is build-local.
set(_nsx_modules_file "${CMAKE_BINARY_DIR}/nsx/modules.cmake")
if(NOT EXISTS "${_nsx_modules_file}")
    message(FATAL_ERROR
        "NSX module inputs are missing for this build directory. Run nsx configure "
        "--app-dir \"${CMAKE_SOURCE_DIR}\" --board ${NSX_BOARD} "
        "--build-dir \"${CMAKE_BINARY_DIR}\" first.")
endif()
include("${_nsx_modules_file}")
if(NOT "${NSX_GENERATED_MODULE_BOARD}" STREQUAL "${NSX_BOARD}")
    message(FATAL_ERROR
        "NSX module inputs belong to ${NSX_GENERATED_MODULE_BOARD}, not ${NSX_BOARD}. "
        "Run nsx configure for the selected board and build directory.")
endif()
unset(_nsx_modules_file)
