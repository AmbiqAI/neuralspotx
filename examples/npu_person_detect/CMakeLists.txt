cmake_minimum_required(VERSION 3.24)
project(npu_person_detect LANGUAGES C CXX ASM)

set(NSX_BOARD "atomiq110_fpga_turbo" CACHE STRING "Target board")

# Compile heliaRT's ethos-u custom-op kernel against the real Ethos-U core
# driver (provided by the nsx-npu module) instead of the null stub.
set(NSX_HELIA_RT_ENABLE_ETHOSU ON CACHE BOOL
    "Enable heliaRT Ethos-U custom-op dispatch")

# NSX_HELIA_RT_BACKEND=helia (heliaRT's default) requires ns-cmsis-nn's fp32
# kernels. Must be set before nsx-cmsis-nn is added (see
# modules/ns-cmsis-nn/nsx/CMakeLists.txt) — hence before nsx_bootstrap_app().
set(NSX_CMSIS_NN_ENABLE_F32 ON CACHE BOOL
    "Enable ns-cmsis-nn fp32 kernels required by heliaRT")

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
add_executable(npu_person_detect
    src/main.cc
)

target_include_directories(npu_person_detect PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_link_libraries(npu_person_detect PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::helia_rt
    nsx::npu
)

nsx_finalize_app(npu_person_detect)
