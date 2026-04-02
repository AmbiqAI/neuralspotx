cmake_minimum_required(VERSION 3.24)
project(usb_rpc LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(usb_rpc
    src/main.c
    src/nsx_rpc_dispatch.c
    # Pre-generated protobuf sources (from proto/nsx_rpc.proto)
    proto/nsx_rpc.pb.c
)

target_include_directories(usb_rpc PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
    ${CMAKE_CURRENT_LIST_DIR}/proto
)

target_link_libraries(usb_rpc PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::usb
    nsx::nanopb
)

nsx_finalize_app(usb_rpc)
