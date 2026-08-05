cmake_minimum_required(VERSION 3.24)
project(executorch_add LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")
set(NSX_EXECUTORCH_SELECT_OPS_LIST "aten::add.out" CACHE STRING
    "Operators required by model/add.pte")

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
set(MODEL_PTE "${CMAKE_CURRENT_LIST_DIR}/model/add.pte")
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

add_executable(executorch_add src/main.cc "${MODEL_HEADER}")
target_include_directories(executorch_add PRIVATE "${MODEL_HEADER_DIR}")
target_link_libraries(executorch_add PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::executorch
)

nsx_finalize_app(executorch_add)
