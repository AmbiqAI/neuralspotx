# SPDX-License-Identifier: BSD-3-Clause
set(platform "${ARM_DEPS}/ethos-u-core-platform")
set(device "${ARM_DEPS}/Cortex_DFP/Device/ARMCM55")
set(UART0_BASE 0x49303000)
set(SYSTEM_CORE_CLOCK 25000000)
add_subdirectory("${platform}/drivers/uart" arm-uart)

set(linker_input "${platform}/targets/corstone-300/platform.ld")
set(linker_output "${CMAKE_CURRENT_BINARY_DIR}/platform.ld")
add_custom_command(
    OUTPUT "${linker_output}"
    COMMAND "${CMAKE_C_COMPILER}" -E -x c -P -DETHOSU_MODEL=0 -DETHOSU_ARENA=0
        "${linker_input}" -o "${linker_output}"
    DEPENDS "${linker_input}" VERBATIM
)
set_property(TARGET pilot APPEND PROPERTY LINK_DEPENDS "${linker_output}")
target_sources(pilot PRIVATE
    corstone_console.c "${linker_output}"
    "${platform}/targets/corstone-300/retarget.c"
    "${device}/Source/startup_ARMCM55.c" "${device}/Source/system_ARMCM55.c"
)
target_include_directories(pilot PRIVATE
    "${ARM_DEPS}/CMSIS_6/CMSIS/Core/Include" "${device}/Include" "${device}/Config"
)
target_compile_definitions(pilot PRIVATE ARMCM55 CMSIS_device_header="ARMCM55.h")
target_compile_options(pilot PRIVATE -include ARMCM55.h)
target_link_libraries(pilot PRIVATE ethosu_uart_cmsdk_apb)
target_link_options(pilot PRIVATE --specs=nosys.specs "-T${linker_output}")
