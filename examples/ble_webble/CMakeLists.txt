# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
cmake_minimum_required(VERSION 3.24)
project(ble_webble LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo4p_blue_kxr_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

# FreeRTOSConfig.h is application policy, not SDK policy. nsx-freertos consumes
# it through the nsx::freertos_config interface contract, so the app must
# publish that target BEFORE the bootstrap adds nsx-freertos (and nsx-ble,
# which depends on it).
add_library(app_freertos_config INTERFACE)
target_include_directories(app_freertos_config INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/config
)
add_library(nsx::freertos_config ALIAS app_freertos_config)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

add_executable(ble_webble
    src/main.c
)

target_link_libraries(ble_webble PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::freertos
    nsx::ble
)

nsx_finalize_app(ble_webble)

# A deliberately small secondary image used to exercise NSX named-target
# build and flash support on the same generated project. EXCLUDE_FROM_ALL
# keeps the normal BLE example build unchanged.
add_executable(ble_webble_flash_probe EXCLUDE_FROM_ALL
    src/flash_probe.c
)

target_link_libraries(ble_webble_flash_probe PRIVATE
    nsx::board
    nsx::runtime_core
)

nsx_finalize_app(ble_webble_flash_probe)
