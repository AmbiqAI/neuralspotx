cmake_minimum_required(VERSION 3.24)
project(pmu_profiling LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(pmu_profiling
    src/main.c
)

target_link_libraries(pmu_profiling PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::pmu_armv8m
)

nsx_finalize_app(pmu_profiling)
