cmake_minimum_required(VERSION 3.24)
project(audio_capture LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(audio_capture
    src/main.c
)

target_link_libraries(audio_capture PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::audio
)

nsx_finalize_app(audio_capture)
