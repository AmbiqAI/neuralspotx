# atomiq110_fpga_turbo board aggregator.
include("${CMAKE_CURRENT_LIST_DIR}/soc.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/bsp.cmake")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

include("${CMAKE_CURRENT_LIST_DIR}/memory.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/debug.cmake")

set(NSX_BOARD_TARGET nsx_board_atomiq110_fpga_turbo)
set(NSX_BOARD_FLAGS_TARGET nsx_board_atomiq110_fpga_turbo_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_atomiq110")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_atomiq110")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_atomiq110_fpga_turbo")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_atomiq110_fpga_turbo")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_atomiq110_fpga_turbo ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    atomiq110_fpga_turbo
    AM_PACKAGE_BGA
    AM_PART_ATOMIQ110
    STACK_SIZE=4096
)

nsx_apply_toolchain_flags(${NSX_BOARD_FLAGS_TARGET})

target_link_libraries(${NSX_BOARD_FLAGS_TARGET} INTERFACE ${NSX_SOC_FLAGS_TARGET})
target_link_libraries(${NSX_BOARD_TARGET} INTERFACE ${NSX_BOARD_FLAGS_TARGET})

install(TARGETS
    ${NSX_BOARD_TARGET}
    ${NSX_BOARD_FLAGS_TARGET}
    EXPORT nsxTargets
)