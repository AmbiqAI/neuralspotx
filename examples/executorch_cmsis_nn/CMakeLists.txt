cmake_minimum_required(VERSION 3.24)
project(executorch_cmsis_nn LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")
set(NSX_EXECUTORCH_CORTEX_M_SELECT_OPS_LIST
    "cortex_m::quantize_per_tensor.out;cortex_m::quantized_conv2d.out;cortex_m::dequantize_per_tensor.out"
    CACHE STRING "Operators required by model/conv2d_cmsis_nn.pte")

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
set(MODEL_PTE "${CMAKE_CURRENT_LIST_DIR}/model/conv2d_cmsis_nn.pte")
set(PTE_TO_HEADER
    "${CMAKE_CURRENT_LIST_DIR}/modules/executorch/examples/arm/executor_runner/pte_to_header.py")

add_custom_command(
    OUTPUT "${MODEL_HEADER}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${MODEL_HEADER_DIR}"
    COMMAND ${Python3_EXECUTABLE} "${PTE_TO_HEADER}"
            --pte "${MODEL_PTE}" --outdir "${MODEL_HEADER_DIR}"
            --section .data.model_pte
    DEPENDS "${MODEL_PTE}" "${PTE_TO_HEADER}"
    VERBATIM
)

add_executable(executorch_cmsis_nn src/main.cc "${MODEL_HEADER}")
target_include_directories(executorch_cmsis_nn PRIVATE
    "${MODEL_HEADER_DIR}"
    "${CMAKE_CURRENT_LIST_DIR}/src"
)
target_link_libraries(executorch_cmsis_nn PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::executorch
)

nsx_finalize_app(executorch_cmsis_nn)

add_custom_command(TARGET executorch_cmsis_nn POST_BUILD
    COMMAND ${CMAKE_COMMAND}
            -DNM=${CMAKE_NM}
            -DELF=$<TARGET_FILE:executorch_cmsis_nn>
            -P "${CMAKE_CURRENT_LIST_DIR}/cmake/verify_cmsis_nn_symbols.cmake"
    VERBATIM
)
