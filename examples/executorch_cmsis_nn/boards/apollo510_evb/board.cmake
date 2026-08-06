# apollo510_evb board aggregator (issue #154a).
#
# Stable include entry point (nsx_app_bootstrap.cmake includes
# "${NSX_ROOT}/boards/${NSX_BOARD}/board.cmake"). Wires the role
# fragments in declaration order, then creates the board interface
# targets. Per-role wiring lives in sibling fragments so individual
# roles can be swapped without rewriting the whole board:
#   soc.cmake    - SoC fact load + nsx::soc_flags
#   bsp.cmake    - SDK provider precondition + AmbiqSuite BSP/MCU/HAL locations
#   memory.cmake - startup/system sources + linker-script selection
#   debug.cmake  - debug-probe / SEGGER device facts
include("${CMAKE_CURRENT_LIST_DIR}/soc.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/bsp.cmake")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

include("${CMAKE_CURRENT_LIST_DIR}/memory.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/debug.cmake")

set(NSX_BOARD_TARGET nsx_board_apollo510_evb)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo510_evb_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo510")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo510")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo510_evb")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo510_evb")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo510_evb ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    apollo510_evb
    # AM_PACKAGE_BGA: AmbiqSuite chip-package selector (ball-grid-array
    # variant); gates package-specific pin/peripheral config in the SDK.
    AM_PACKAGE_BGA
    # STACK_SIZE: startup C-runtime stack size in bytes (used by SDK startup).
    STACK_SIZE=4096
)

# Compile options set by nsx_apply_toolchain_flags() below

# Link options set by nsx_apply_toolchain_flags() below

nsx_apply_toolchain_flags(${NSX_BOARD_FLAGS_TARGET})

# board_flags carries the SoC flags so that nsx::soc_hal (which links
# nsx::board_flags) and every downstream consumer (core, FreeRTOS port) sees
# the full SoC define set.
target_link_libraries(${NSX_BOARD_FLAGS_TARGET} INTERFACE ${NSX_SOC_FLAGS_TARGET})
target_link_libraries(${NSX_BOARD_TARGET} INTERFACE ${NSX_BOARD_FLAGS_TARGET})

install(TARGETS
    ${NSX_BOARD_TARGET}
    ${NSX_BOARD_FLAGS_TARGET}
    EXPORT nsxTargets
)
