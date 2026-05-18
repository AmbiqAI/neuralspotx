set(NSX_SOC_FAMILY "atomiq110")
set(NSX_CPU "cortex-m55")
set(NSX_FLOAT_ABI "hard")
set(NSX_ABI_FLAGS "thumbv8.1m-fpv5-hard")

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r6")
    message(FATAL_ERROR
        "atomiq110_fpga_turbo requires NSX_SDK_PROVIDER=ambiqsuite-r6, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "atomiq110_fpga_turbo")
set(NSX_AMBIQ_PART_NAME "atomiq110")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_ROOT}/modules/nsx-core/src/atomiq110/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/atomiq110/system_atomiq110.c")
    set(NSX_LINKER_SCRIPT "${NSX_ROOT}/modules/nsx-core/src/atomiq110/armclang/linker_script_sbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_ROOT}/modules/nsx-core/src/atomiq110/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/atomiq110/system_atomiq110.c")
    set(NSX_LINKER_SCRIPT "${NSX_ROOT}/modules/nsx-core/src/atomiq110/gcc/linker_script_sbl.ld")
endif()

include("${NSX_CMAKE_DIR}/segger/socs/apollo5.cmake")

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
    NEURALSPOT
    atomiq110_fpga_turbo
    PART_atomiq110
    AM_PART_ATOMIQ110
    ARMCM55
    AM_PACKAGE_BGA
    __FPU_PRESENT
    STACK_SIZE=4096
)

# Compile options set by nsx_apply_toolchain_flags() below

# Link options set by nsx_apply_toolchain_flags() below

nsx_apply_toolchain_flags(${NSX_BOARD_FLAGS_TARGET})

target_link_libraries(${NSX_BOARD_TARGET} INTERFACE ${NSX_BOARD_FLAGS_TARGET})

install(TARGETS
    ${NSX_BOARD_TARGET}
    ${NSX_BOARD_FLAGS_TARGET}
    EXPORT nsxTargets
)
