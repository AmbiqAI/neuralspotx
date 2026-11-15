# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# Prepared inputs live in the source tree, independently of build directories.
function(_nsx_check_compiler)
    if(CMAKE_C_COMPILER_LOADED AND NOT CMAKE_C_COMPILER_ID IN_LIST ARGN)
        message(FATAL_ERROR
            "Compiler '${CMAKE_C_COMPILER_ID}' is not supported by the prepared NSX modules. "
            "Select a compatible toolchain and run nsx lock then nsx sync.")
    endif()
endfunction()

function(_nsx_check_metadata relative expected)
    set(path "${CMAKE_SOURCE_DIR}/${relative}")
    # Glob membership catches creation/deletion, including initially absent
    # optional manifests; configure dependencies catch edits during --build.
    file(GLOB observed CONFIGURE_DEPENDS "${path}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${path}")
    set(actual "absent")
    if(EXISTS "${path}" AND NOT IS_DIRECTORY "${path}")
        file(SHA256 "${path}" actual)
    endif()
    if(NOT "${actual}" STREQUAL "${expected}")
        message(FATAL_ERROR
            "NSX declaration '${relative}' changed since preparation. "
            "Run nsx lock then nsx sync for ${NSX_BOARD}.")
    endif()
endfunction()

function(_nsx_require_file relative)
    if(NOT EXISTS "${CMAKE_SOURCE_DIR}/${relative}")
        message(FATAL_ERROR
            "NSX dependency '${relative}' is missing. Run nsx sync before sharing this app.")
    endif()
endfunction()

set(_nsx_modules_file "${CMAKE_SOURCE_DIR}/cmake/nsx-resolved/${NSX_BOARD}/modules.cmake")
if(NOT EXISTS "${_nsx_modules_file}")
    # Compatibility for apps not yet prepared by create-app or sync. These
    # inputs do not enable fresh standalone builds; they retain old NSX builds.
    set(_nsx_modules_file "${CMAKE_BINARY_DIR}/nsx/modules.cmake")
endif()
if(NOT EXISTS "${_nsx_modules_file}")
    message(FATAL_ERROR
        "NSX module inputs are missing. Run nsx configure "
        "--app-dir \"${CMAKE_SOURCE_DIR}\" --board ${NSX_BOARD} first, "
        "or nsx sync to prepare standalone CMake inputs.")
endif()
include("${_nsx_modules_file}")
if(NOT "${NSX_GENERATED_MODULE_BOARD}" STREQUAL "${NSX_BOARD}")
    message(FATAL_ERROR
        "NSX module inputs belong to ${NSX_GENERATED_MODULE_BOARD}, not ${NSX_BOARD}. "
        "Run nsx configure for the selected board and build directory.")
endif()
unset(_nsx_modules_file)
