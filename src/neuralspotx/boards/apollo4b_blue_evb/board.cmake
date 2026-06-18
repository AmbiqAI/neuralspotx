# SoC facts (NSX_SOC_* + NSX_CPU/NSX_FPU/NSX_FLOAT_ABI/NSX_ABI_FLAGS) come from
# the nsx-ambiq-sdk single source of truth so they cannot drift from the SDK's
# own SoC descriptor. This also publishes the RTOS port facts the optional
# nsx-freertos module consumes. nsx_load_soc_facts() is provided by the SDK's
# auto-included cmake/nsx_soc_facts.cmake.
nsx_load_soc_facts("apollo4p")

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r4")
    message(FATAL_ERROR
        "apollo4b_blue_evb requires NSX_SDK_PROVIDER=ambiqsuite-r4, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo4b_blue_evb")
set(NSX_AMBIQ_PART_NAME "apollo4b")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
# Apollo4B reuses the Apollo4P MCU/HAL directory layout in AmbiqSuite r4.
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/apollo4p")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

# Apollo4B shares the prebuilt HAL library with Apollo4P
set(NSX_HAL_LIB "${NSX_AMBIQSUITE_ROOT}/lib/apollo4p/libam_hal.a" CACHE FILEPATH "" FORCE)

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4p/armclang/startup_armclang.s")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4p/armclang/linker_script.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4p/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4p/gcc/linker_script.ld")
endif()

# Keep the Apollo4B Blue EVB on the Apollo4P KBR target until a distinct
# Apollo4B-specific J-Link device ID is verified in-tree.
set(NSX_SEGGER_DEVICE "AMAP42KP-KBR")

include("${NSX_CMAKE_DIR}/segger/socs/apollo4p.cmake")

set(NSX_BOARD_TARGET nsx_board_apollo4b_blue_evb)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo4b_blue_evb_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo4p")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo4p")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo4b_blue_evb")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo4b_blue_evb")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo4b_blue_evb ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    apollo4b_blue_evb
    PART_apollo4b
    AM_PART_APOLLO4B
    AM_PACKAGE_BGA
    __FPU_PRESENT
    STACK_SIZE=4096
)

nsx_apply_toolchain_flags(${NSX_BOARD_FLAGS_TARGET})

target_link_libraries(${NSX_BOARD_TARGET} INTERFACE ${NSX_BOARD_FLAGS_TARGET})

install(TARGETS
    ${NSX_BOARD_TARGET}
    ${NSX_BOARD_FLAGS_TARGET}
    EXPORT nsxTargets
)
