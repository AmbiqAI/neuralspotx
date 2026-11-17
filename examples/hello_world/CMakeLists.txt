cmake_minimum_required(VERSION 3.24)
project(hello_world LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

# Audited baseline: Apollo510 EVB/GCC. Re-audit external setting inputs when
# changing modules or board logic; use nsx_debug_read_text for data inputs.
if(NSX_BOARD STREQUAL "apollo510_evb" AND CMAKE_C_COMPILER_ID STREQUAL "GNU"
   AND CMAKE_SYSTEM_PROCESSOR STREQUAL "arm")
    option(NSX_DEBUG_CONTEXT "Prepare configured debug handoff" ON)
    set(NSX_DEBUG_INPUT_CONTRACT 1)
endif()


include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(hello_world
    src/main.c
)

target_link_libraries(hello_world PRIVATE
    nsx::board
    nsx::runtime_core
)

nsx_finalize_app(hello_world)

if(NSX_DEBUG_CONTEXT)
    nsx_debug_set_primary_target(hello_world)
endif()
