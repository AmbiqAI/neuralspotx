# SoC facts (NSX_SOC_* + NSX_CPU/NSX_FPU/NSX_FLOAT_ABI/NSX_ABI_FLAGS) come from
# the nsx-ambiq-sdk single source of truth so they cannot drift from the SDK's
# own SoC descriptor. This also publishes the RTOS port facts the optional
# nsx-freertos module consumes. nsx_load_soc_facts() is provided by the SDK's
# auto-included cmake/nsx_soc_facts.cmake.
nsx_load_soc_facts("apollo510L")

if(DEFINED NSX_SOC_PMU_TIER AND NSX_SOC_PMU_TIER STREQUAL "armv8m")
    set(NSX_AMBIQ_HAL_HAS_PMU TRUE)
endif()

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite")
    message(FATAL_ERROR
        "apollo510dL_evb requires NSX_SDK_PROVIDER=ambiqsuite, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo510dL_evb")
set(NSX_AMBIQ_PART_NAME "apollo510L")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510L/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/apollo510L/system_apollo510L.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510L/armclang/linker_script_sbl.sct")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510L/armclang/linker_script_itcm_sbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510L/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/apollo510L/system_apollo510L.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510L/gcc/linker_script_sbl.ld")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510L/gcc/linker_script_itcm_sbl.ld")
endif()

if(NOT DEFINED NSX_LINKER_SCRIPT)
    if(COMMAND nsx_select_linker_script)
        nsx_select_linker_script(
            DEFAULT "${_nsx_linker_script_default}"
            ITCM "${_nsx_linker_script_itcm}"
        )
    else()
        # SDK predates named linker profiles — fall back to the default script.
        set(NSX_LINKER_SCRIPT "${_nsx_linker_script_default}")
    endif()
endif()

include("${NSX_CMAKE_DIR}/segger/socs/apollo330.cmake")

set(NSX_BOARD_TARGET nsx_board_apollo510dL_evb)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo510dL_evb_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo510L")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo510L")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo510dL_evb")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo510dL_evb")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo510dL_evb ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    apollo510dL_evb
    PART_apollo510L
    AM_PART_APOLLO510L
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
