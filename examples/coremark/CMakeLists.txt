cmake_minimum_required(VERSION 3.24)
project(coremark LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

# Preserve CoreMark output until the host connects; explicit cache overrides win.
set(NSX_SEGGER_RTT_BUFFER_SIZE_UP 32768 CACHE STRING "RTT channel 0 up buffer bytes")

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

# ---------------------------------------------------------------------------
# CoreMark sources (EEMBC, Apache-2.0)
# ---------------------------------------------------------------------------
set(COREMARK_DIR ${CMAKE_CURRENT_LIST_DIR}/src/coremark)

add_executable(coremark
    # CoreMark core (upstream EEMBC)
    ${COREMARK_DIR}/core_main.c
    ${COREMARK_DIR}/core_list_join.c
    ${COREMARK_DIR}/core_matrix.c
    ${COREMARK_DIR}/core_state.c
    ${COREMARK_DIR}/core_util.c
    # Platform port (NSX)
    src/core_portme.c
)

target_include_directories(coremark PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src          # core_portme.h
    ${COREMARK_DIR}                        # coremark.h
)

# Compiler flags string for CoreMark reporting
target_compile_definitions(coremark PRIVATE
    FLAGS_STR="${CMAKE_C_FLAGS}"
    ITERATIONS=0                           # auto-calibrate
    PERFORMANCE_RUN=1
)

target_link_libraries(coremark PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::timer
    nsx::segger_rtt
)

nsx_finalize_app(coremark)
