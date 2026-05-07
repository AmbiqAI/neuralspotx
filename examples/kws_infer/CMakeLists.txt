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

# Build-variant selector (release | release-with-logs | debug). Keep "with-logs"
# as the default so MicroPrintf output is captured during bring-up; switch to
# "release" for power/perf measurements.
set(HELIART_VARIANT "release-with-logs" CACHE STRING
    "HeliaRT prebuilt variant: release | release-with-logs | debug")
set_property(CACHE HELIART_VARIANT PROPERTY STRINGS release release-with-logs debug)

# Map NSX_CPU -> HeliaRT CPU tag.
if(NSX_CPU STREQUAL "cortex-m55")
    set(_heliart_cpu "cm55")
elseif(NSX_CPU STREQUAL "cortex-m4")
    set(_heliart_cpu "cm4")
else()
    message(FATAL_ERROR
        "kws_infer: no HeliaRT prebuilt available for CPU '${NSX_CPU}'. "
        "Supported: cortex-m55, cortex-m4.")
endif()

# Toolchain selector. ATfE has no prebuilt — fail loudly rather than silently
# linking a GCC/armclang lib with a different ABI (libgcc vs compiler-rt
# helpers, EH tables, etc). With -fshort-enums now uniform across all three
# toolchains, the remaining ABI gap is the runtime helper library, which is
# not interchangeable.
if(NSX_TOOLCHAIN_FAMILY STREQUAL "gcc")
    set(_heliart_tc "gcc")
elseif(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(_heliart_tc "armclang")
else()
    message(FATAL_ERROR
        "kws_infer: HeliaRT v1.7.0 has no prebuilt for toolchain "
        "'${NSX_TOOLCHAIN_FAMILY}'. Available: gcc, armclang. "
        "Rebuild with -DCMAKE_TOOLCHAIN_FILE pointing at the GCC or armclang "
        "toolchain file under src/neuralspotx/cmake/toolchains/.")
endif()

set(_heliart_lib
    "${HELIART_ROOT}/lib/libtensorflow-microlite-${_heliart_cpu}-${_heliart_tc}-${HELIART_VARIANT}.a")
nsx_assert_file_exists("${_heliart_lib}")

add_library(heliart STATIC IMPORTED)
set_target_properties(heliart PROPERTIES
    IMPORTED_LOCATION "${_heliart_lib}"
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
