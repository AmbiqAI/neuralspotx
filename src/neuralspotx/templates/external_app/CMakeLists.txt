cmake_minimum_required(VERSION 3.24)
project(__NSX_APP_NAME__ LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

option(FOO_USE_NSX_PORTABLE "Link nsx::portable_api in addition to runtime core" OFF)

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(__NSX_APP_NAME__
    src/main.c
)

target_link_libraries(__NSX_APP_NAME__ PRIVATE
    nsx::board
    nsx::runtime_core
)

if(FOO_USE_NSX_PORTABLE)
    target_link_libraries(__NSX_APP_NAME__ PRIVATE nsx::portable_api)
endif()
nsx_finalize_app(__NSX_APP_NAME__)
