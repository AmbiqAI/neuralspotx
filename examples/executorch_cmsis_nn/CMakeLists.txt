cmake_minimum_required(VERSION 3.24)
project(executorch_cmsis_nn LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")
set(NSX_EXECUTORCH_CMSIS_NN_PROVIDER "arm" CACHE STRING
    "CMSIS-NN provider for ExecuTorch Cortex-M kernels: arm or ns")
set_property(CACHE NSX_EXECUTORCH_CMSIS_NN_PROVIDER PROPERTY STRINGS arm ns)
set(NSX_EXECUTORCH_PTE
    "${CMAKE_CURRENT_LIST_DIR}/model/resnet8_cmsis_nn.pte"
    CACHE FILEPATH "Prebuilt ExecuTorch PTE to embed in the runner")
set(NSX_EXECUTORCH_VALIDATION_HEADER
    "${CMAKE_CURRENT_LIST_DIR}/src/validation_data.h"
    CACHE FILEPATH "Validation input/output contract for the supplied PTE")
set(NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST
    "cortex_m::quantize_per_tensor.out;cortex_m::quantized_conv2d.out;cortex_m::quantized_add.out;cortex_m::quantized_max_pool2d.out;cortex_m::quantized_avg_pool2d.out;cortex_m::quantized_linear.out;cortex_m::transpose.out;cortex_m::dequantize_per_tensor.out"
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

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
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
            -DPROVIDER=${NSX_EXECUTORCH_CMSIS_NN_PROVIDER}
            -DMAP=$<TARGET_FILE_DIR:executorch_cmsis_nn>/executorch_cmsis_nn.map
            -P "${CMAKE_CURRENT_LIST_DIR}/cmake/verify_cmsis_nn_symbols.cmake"
    VERBATIM
)
