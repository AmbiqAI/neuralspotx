# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/common.cmake")

# The initial capture contract supports the existing single-image sequence.
# Comparing the direct rendering alone cannot detect a hard-coded LoadFile path.
# Reject extra commands/file references instead of guessing Commander semantics.
function(_nsx_debug_recipe_commands script out)
    string(REPLACE "\r\n" "\n" lines "${script}")
    string(REPLACE ";" "\\;" lines "${lines}")
    string(REPLACE "\n" ";" lines "${lines}")
    set(commands "")
    foreach(line IN LISTS lines)
        string(STRIP "${line}" line)
        if(line STREQUAL "" OR line MATCHES "^//")
            continue()
        endif()
        string(FIND "${line}" ";" separator)
        if(NOT separator EQUAL -1)
            nsx_debug_fail("unsupported captured recipe command separator")
        endif()
        list(APPEND commands "${line}")
    endforeach()
    set(${out} "${commands}" PARENT_SCOPE)
endfunction()

function(nsx_debug_validate_flash_recipe script binary address)
    _nsx_debug_recipe_commands("${script}" commands)
    set(expected "ExitOnError 1" "Reset" "LoadFile \"${binary}\", ${address}" "Reset" "Go" "Exit")
    if(NOT commands STREQUAL expected)
        nsx_debug_fail("unsupported captured flash recipe: require the standard single-image sequence, copied binary, recorded address and ExitOnError 1")
    endif()
endfunction()

function(nsx_debug_validate_reset_recipe script)
    _nsx_debug_recipe_commands("${script}" commands)
    set(expected "ExitOnError 1" "Reset" "Go" "Exit")
    if(NOT commands STREQUAL expected)
        nsx_debug_fail("unsupported captured SWO reset recipe: require ExitOnError 1, Reset, Go and Exit only")
    endif()
endfunction()
