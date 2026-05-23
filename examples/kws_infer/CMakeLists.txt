cmake_minimum_required(VERSION 3.24)
project(kws_infer LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")
set(HELIA_RT_VARIANT "release-with-logs" CACHE STRING
    "heliaRT build variant: debug | release-with-logs | release")
set_property(CACHE HELIA_RT_VARIANT PROPERTY STRINGS release release-with-logs debug)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
add_executable(kws_infer
    src/main.cc
    src/nsx_pmu_profiler.cc
)

target_include_directories(kws_infer PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_link_libraries(kws_infer PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::power
    nsx::pmu_armv8m
    nsx::helia_rt
)

nsx_finalize_app(kws_infer)
