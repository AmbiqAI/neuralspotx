set(NSX_SOC_FAMILY "apollo3")
set(NSX_CPU "cortex-m4")
set(NSX_FPU "fpv4-sp-d16")
set(NSX_FLOAT_ABI "hard")
set(NSX_ABI_FLAGS "thumbv7em-fpv4sp-hard")

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r3")
    message(FATAL_ERROR
        "apollo3_evb_cygnus requires NSX_SDK_PROVIDER=ambiqsuite-r3, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo3_evb_cygnus")
set(NSX_AMBIQ_PART_NAME "apollo3")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

set(NSX_STARTUP_SOURCE "${NSX_ROOT}/modules/nsx-core/src/apollo3/gcc/startup_gcc.c")
set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo3.c")
set(NSX_LINKER_SCRIPT "${NSX_ROOT}/modules/nsx-core/src/apollo3/gcc/linker_script.ld")
include("${NSX_CMAKE_DIR}/segger/socs/apollo3p.cmake")

set(NSX_BOARD_TARGET nsx_board_apollo3_evb_cygnus)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo3_evb_cygnus_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo3")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo3")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo3_evb_cygnus")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo3_evb_cygnus")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo3_evb_cygnus ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    NEURALSPOT
    apollo3_evb_cygnus
    PART_apollo3
    PART_APOLLO3
    AM_PART_APOLLO3
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
