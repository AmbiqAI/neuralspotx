# SoC facts (NSX_SOC_* + NSX_CPU/NSX_FPU/NSX_FLOAT_ABI/NSX_ABI_FLAGS) come from
# the nsx-ambiq-sdk single source of truth so they cannot drift from the SDK's
# own SoC descriptor. This also publishes the RTOS port facts the optional
# nsx-freertos module consumes. nsx_load_soc_facts() is provided by the SDK's
# auto-included cmake/nsx_soc_facts.cmake.
nsx_load_soc_facts("apollo3")

# nsx::soc_flags carries all SoC-owned compile definitions, derived from the
# SoC facts loaded above. Named to match the SDK's own SoC descriptor flags
# target. The board links it below rather than re-declaring SoC macros.
set(NSX_SOC_FLAGS_TARGET nsx_soc_apollo3_flags)
nsx_soc_flags_target(${NSX_SOC_FLAGS_TARGET})

if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite")
    message(FATAL_ERROR
        "apollo3_evb requires NSX_SDK_PROVIDER=ambiqsuite, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo3_evb")
set(NSX_AMBIQ_PART_NAME "apollo3")
set(NSX_AMBIQ_BSP_LIB_SUBDIR "apollo3_evb")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

include("${NSX_CMAKE_DIR}/nsx_toolchain_flags.cmake")

nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo3/gcc/startup_gcc.c")
set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo3.c")
set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo3/gcc/linker_script.ld")
set(NSX_BOARD_TARGET nsx_board_apollo3_evb)
set(NSX_BOARD_FLAGS_TARGET nsx_board_apollo3_evb_flags)
set(NSX_SOC_TARGET_EXPORT_NAME "soc_hal_apollo3")
set(NSX_STARTUP_TARGET_EXPORT_NAME "startup_apollo3")
set(NSX_BOARD_TARGET_EXPORT_NAME "board_apollo3_evb")
set(NSX_BOARD_FLAGS_TARGET_EXPORT_NAME "board_flags_apollo3_evb")

nsx_assert_file_exists("${NSX_LINKER_SCRIPT}")
nsx_assert_file_exists("${NSX_STARTUP_SOURCE}")
nsx_assert_file_exists("${NSX_SYSTEM_SOURCE}")

add_library(${NSX_BOARD_TARGET} INTERFACE)
add_library(${NSX_BOARD_FLAGS_TARGET} INTERFACE)
set_target_properties(${NSX_BOARD_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_TARGET_EXPORT_NAME})
set_target_properties(${NSX_BOARD_FLAGS_TARGET} PROPERTIES EXPORT_NAME ${NSX_BOARD_FLAGS_TARGET_EXPORT_NAME})

add_library(nsx::board ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_apollo3_evb ALIAS ${NSX_BOARD_TARGET})
add_library(nsx::board_flags ALIAS ${NSX_BOARD_FLAGS_TARGET})

target_compile_definitions(${NSX_BOARD_FLAGS_TARGET} INTERFACE
    apollo3_evb
    PART_APOLLO3
    AM_PACKAGE_BGA
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
