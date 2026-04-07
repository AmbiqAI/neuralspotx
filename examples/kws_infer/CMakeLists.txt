cmake_minimum_required(VERSION 3.24)
project(kws_infer LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

# ---------------------------------------------------------------------------
# HeliaRT v1.7.0 prebuilt (not yet an nsx module — linked directly)
# ---------------------------------------------------------------------------
# Resolve workspace root (neuralspot monorepo) from example location.
get_filename_component(_WS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(HELIART_ROOT "${_WS_ROOT}/neuralspot/extern/tensorflow/helia_rt_v1_7_0")

add_library(heliart STATIC IMPORTED)
set_target_properties(heliart PROPERTIES
    IMPORTED_LOCATION "${HELIART_ROOT}/lib/libtensorflow-microlite-cm55-gcc-release-with-logs.a"
)
target_include_directories(heliart INTERFACE
    "${HELIART_ROOT}"
    "${HELIART_ROOT}/third_party"
    "${HELIART_ROOT}/third_party/flatbuffers/include"
    "${HELIART_ROOT}/third_party/gemmlowp"
)
target_compile_definitions(heliart INTERFACE
    TF_LITE_STATIC_MEMORY
    NS_TFSTRUCTURE_RECENT
    NS_TFLM_NEW_MICRO_PROFILER
)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
add_executable(kws_infer
    src/main.cc
    src/nsx_pmu_profiler.cc
    # TFLM support sources not in the prebuilt lib (needed for MicroPrintf / DebugLog)
    ${HELIART_ROOT}/tensorflow/lite/micro/micro_log.cc
    ${HELIART_ROOT}/tensorflow/lite/micro/cortex_m_generic/debug_log.cc
)

target_include_directories(kws_infer PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_link_libraries(kws_infer PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::power
    nsx::pmu_armv8m
    heliart
)

nsx_finalize_app(kws_infer)
