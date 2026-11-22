# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
set(NSX_CPU cortex-m85)
set(NSX_SOC_FAMILY corstone320)
set(NSX_TOOLCHAIN_FAMILY gcc)
set(NSX_BOARD_TARGET nsx_board_corstone320_fvp_u85)
add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_corstone320_fvp_u85 ALIAS ${NSX_BOARD_TARGET})
target_compile_definitions(${NSX_BOARD_TARGET} INTERFACE NSX_PLATFORM_CORSTONE=1)
