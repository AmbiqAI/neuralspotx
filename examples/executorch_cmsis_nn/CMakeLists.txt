cmake_minimum_required(VERSION 3.24)
project(executorch_cmsis_nn LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")
# NOT FORCEd: pass -DNSX_EXECUTORCH_CMSIS_NN_PROVIDER=ns at configure time to
# switch providers without editing this file or re-running `nsx lock`/`nsx
# sync` (both arm-cmsis-nn and nsx-cmsis-nn are already vendored below).
set(NSX_EXECUTORCH_CMSIS_NN_PROVIDER "arm" CACHE STRING
    "Stock CMSIS-NN provider for ExecuTorch Cortex-M kernels: arm or ns")
set_property(CACHE NSX_EXECUTORCH_CMSIS_NN_PROVIDER PROPERTY STRINGS arm ns)
set(NSX_EXECUTORCH_ENABLE_PROFILING ON CACHE BOOL
    "Enable total and per-operator ExecuTorch cycle measurements" FORCE)
set(NSX_EXECUTORCH_PTE
    "${CMAKE_CURRENT_LIST_DIR}/model/resnet8_cmsis_nn.pte"
    CACHE FILEPATH "Prebuilt ExecuTorch PTE to embed in the runner")
set(NSX_EXECUTORCH_VALIDATION_HEADER
    "${CMAKE_CURRENT_LIST_DIR}/src/validation_data.h"
    CACHE FILEPATH "Validation input/output contract for the supplied PTE")
set(NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST
    "cortex_m::quantize_per_tensor.out;cortex_m::quantized_conv2d.out;cortex_m::quantized_add.out;cortex_m::quantized_max_pool2d.out;cortex_m::quantized_avg_pool2d.out;cortex_m::transpose.out;cortex_m::dequantize_per_tensor.out"
    CACHE STRING "Cortex-M operators required by the supplied PTE")
set(NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST
    "aten::clamp.out,aten::addmm.out"
    CACHE STRING "Portable ATen fallback operators available to supplied PTEs")

if(NOT EXISTS "${NSX_EXECUTORCH_PTE}")
  message(FATAL_ERROR "Supplied PTE does not exist: ${NSX_EXECUTORCH_PTE}")
endif()
if(NOT EXISTS "${NSX_EXECUTORCH_VALIDATION_HEADER}")
  message(FATAL_ERROR
      "Supplied validation header does not exist: ${NSX_EXECUTORCH_VALIDATION_HEADER}")
endif()

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

# --- CMSIS-NN provider selection --------------------------------------------
# arm-cmsis-nn and nsx-cmsis-nn are listed in nsx.yml's `modules:` purely so
# `nsx lock`/`nsx sync` vendor their pinned source under modules/; they are
# NOT normal bootstrapped app dependencies. nsx-executorch resolves whichever
# provider NSX_EXECUTORCH_CMSIS_NN_PROVIDER selects and points stock
# ExecuTorch's own CMSIS_NN_LOCAL_PATH hook straight at it:
#   - arm: <arm-cmsis-nn root>/external/CMSIS-NN (arm-cmsis-nn's own vendored
#     upstream source; its own wrapper CMakeLists.txt, which creates
#     nsx::arm_cmsis_nn, is never add_subdirectory()'d for this)
#   - ns:  <ns-cmsis-nn root> itself (its upstream-compatible drop-in root)
# Either way, stock ExecuTorch's cortex_m backend is the only thing that
# add_subdirectory()s that path, creating the single `cmsis-nn` target it
# expects. If the generic per-module bootstrap loop below also
# add_subdirectory()d arm-cmsis-nn as a normal module, its wrapper would
# create `cmsis-nn` a first time (via its own `if(NOT TARGET cmsis-nn)`
# guard) before stock ExecuTorch tried to create it a second time from the
# same source — a hard CMake duplicate-target error. So both provider
# modules are excluded from the MODULES list passed to nsx_bootstrap_app().
set(NSX_EXECUTORCH_CMSIS_NN_PROVIDER_MODULES arm-cmsis-nn nsx-cmsis-nn)
set(NSX_APP_BOOTSTRAP_MODULES ${NSX_APP_MODULES})
list(REMOVE_ITEM NSX_APP_BOOTSTRAP_MODULES ${NSX_EXECUTORCH_CMSIS_NN_PROVIDER_MODULES})

# Point nsx-executorch straight at the vendored checkout for the selected
# provider instead of relying on its NSX_ROOT/NSX_APP_MODULE_DIR_<module>
# auto-discovery: the `nsx-cmsis-nn` module name intentionally resolves to
# its `nsx/` NSX entry-point subdirectory (modules/ns-cmsis-nn/nsx), but
# nsx-executorch needs the project's drop-in root (modules/ns-cmsis-nn)
# instead, so an explicit override is the correct contract here.
if(NSX_EXECUTORCH_CMSIS_NN_PROVIDER STREQUAL "arm")
    set(NSX_EXECUTORCH_ARM_CMSIS_NN_ROOT
        "${CMAKE_CURRENT_LIST_DIR}/modules/arm-cmsis-nn" CACHE PATH "" FORCE)
elseif(NSX_EXECUTORCH_CMSIS_NN_PROVIDER STREQUAL "ns")
    set(NSX_EXECUTORCH_NS_CMSIS_NN_ROOT
        "${CMAKE_CURRENT_LIST_DIR}/modules/ns-cmsis-nn" CACHE PATH "" FORCE)
else()
    message(FATAL_ERROR
        "NSX_EXECUTORCH_CMSIS_NN_PROVIDER must be arm or ns, got "
        "'${NSX_EXECUTORCH_CMSIS_NN_PROVIDER}'")
endif()

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_BOOTSTRAP_MODULES}
)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(MODEL_HEADER_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(MODEL_HEADER "${MODEL_HEADER_DIR}/model_pte.h")
set(MODEL_PTE "${NSX_EXECUTORCH_PTE}")
set(PTE_TO_HEADER
    "${CMAKE_CURRENT_LIST_DIR}/cmake/pte_to_header.py")

add_custom_command(
    OUTPUT "${MODEL_HEADER}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MODEL_HEADER_DIR}"
    COMMAND ${Python3_EXECUTABLE} "${PTE_TO_HEADER}"
            --pte "${MODEL_PTE}" --outdir "${MODEL_HEADER_DIR}"
            --section .rodata.model_pte
    DEPENDS "${MODEL_PTE}" "${PTE_TO_HEADER}"
    VERBATIM
)

add_executable(executorch_cmsis_nn src/main.cc "${MODEL_HEADER}")
target_include_directories(executorch_cmsis_nn PRIVATE
    "${MODEL_HEADER_DIR}"
    "${CMAKE_CURRENT_LIST_DIR}/src"
)
target_compile_definitions(executorch_cmsis_nn PRIVATE
    NSX_EXECUTORCH_VALIDATION_HEADER="${NSX_EXECUTORCH_VALIDATION_HEADER}"
)
target_link_libraries(executorch_cmsis_nn PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::executorch
)

nsx_finalize_app(executorch_cmsis_nn)

string(REPLACE ";" "," NSX_EXECUTORCH_VERIFY_CORTEX_M_OPS
       "${NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST}")
string(REPLACE ";" "," NSX_EXECUTORCH_VERIFY_PORTABLE_OPS
       "${NSX_EXECUTORCH_PORTABLE_SELECT_OPS_LIST}")

add_custom_command(TARGET executorch_cmsis_nn POST_BUILD
    COMMAND ${CMAKE_COMMAND}
            -DNM=${CMAKE_NM}
            -DELF=$<TARGET_FILE:executorch_cmsis_nn>
            -DCORTEX_M_OPS=${NSX_EXECUTORCH_VERIFY_CORTEX_M_OPS}
            -DPORTABLE_OPS=${NSX_EXECUTORCH_VERIFY_PORTABLE_OPS}
            -DMAP=$<TARGET_FILE_DIR:executorch_cmsis_nn>/executorch_cmsis_nn.map
            -P "${CMAKE_CURRENT_LIST_DIR}/cmake/verify_cmsis_nn_symbols.cmake"
    VERBATIM
)
