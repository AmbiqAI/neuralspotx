cmake_minimum_required(VERSION 3.24)
project(resnet_example LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

option(FOO_USE_NSX_PORTABLE "Link nsx::portable_api in addition to runtime core" OFF)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(resnet_example
    src/main.c
)

target_link_libraries(resnet_example PRIVATE
    nsx::board_apollo510_evb
    nsx::runtime_core
)

if(TARGET nsx::resnet_aot)
    target_link_libraries(resnet_example PRIVATE nsx::resnet_aot)
    target_compile_definitions(resnet_example PRIVATE RESNET_EXAMPLE_HAS_AOT=1)
else()
    message(STATUS "resnet_example: resnet-aot module not present yet; building tutorial scaffold")
endif()

if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/src/resnet_sample_data.h")
    target_compile_definitions(resnet_example PRIVATE RESNET_EXAMPLE_HAS_SAMPLE_DATA=1)
else()
    message(STATUS "resnet_example: resnet_sample_data.h not present yet; building tutorial scaffold")
endif()

if(FOO_USE_NSX_PORTABLE)
    target_link_libraries(resnet_example PRIVATE nsx::portable_api)
endif()
nsx_finalize_app(resnet_example)
