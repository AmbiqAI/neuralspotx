set(NSX_SOC_FAMILY "apollo4p")
set(NSX_CPU "cortex-m4")
set(NSX_FPU "fpv4-sp-d16")
set(NSX_FLOAT_ABI "hard")
set(NSX_ABI_FLAGS "thumbv7em-fpv4sp-hard")

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r4")
    message(FATAL_ERROR
        "apollo4p_evb requires NSX_SDK_PROVIDER=ambiqsuite-r4, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo4p_evb")
set(NSX_AMBIQ_PART_NAME "apollo4p")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_ROOT}/modules/nsx-core/src/apollo4p/armclang/startup_armclang.s")
    set(NSX_SYSTEM_SOURCE "${NSX_ROOT}/modules/nsx-core/src/apollo4p/armclang/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_ROOT}/modules/nsx-core/src/apollo4p/armclang/linker_script.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_ROOT}/modules/nsx-core/src/apollo4p/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_ROOT}/modules/nsx-core/src/apollo4p/armclang/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_ROOT}/modules/nsx-core/src/apollo4p/gcc/linker_script.ld")
endif()

include("${NSX_CMAKE_DIR}/segger/socs/apollo4p.cmake")

set(NSX_BOARD_TARGET nsx_board_apollo4p_evb)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo4p_evb_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo4p")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo4p")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo4p_evb")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo4p_evb")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo4p_evb ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    NEURALSPOT
    apollo4p_evb
    PART_apollo4p
    AM_PART_APOLLO4P
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
