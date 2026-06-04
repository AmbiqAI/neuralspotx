function(nsx_assert_file_exists path)
    if(NOT EXISTS "${path}")
        message(FATAL_ERROR "Required file does not exist: ${path}")
    endif()
endfunction()

function(nsx_validate_prebuilt_abi)
    if(DEFINED NSX_PREBUILT_SOC_FAMILY AND NOT NSX_PREBUILT_SOC_FAMILY STREQUAL NSX_SOC_FAMILY)
        message(FATAL_ERROR "Prebuilt SOC mismatch. prebuilt=${NSX_PREBUILT_SOC_FAMILY}, board=${NSX_SOC_FAMILY}")
    endif()
    if(DEFINED NSX_PREBUILT_TOOLCHAIN AND NOT NSX_PREBUILT_TOOLCHAIN STREQUAL NSX_TOOLCHAIN_FAMILY)
        message(FATAL_ERROR "Prebuilt toolchain mismatch. prebuilt=${NSX_PREBUILT_TOOLCHAIN}, board=${NSX_TOOLCHAIN_FAMILY}")
    endif()
    if(DEFINED NSX_PREBUILT_ABI_FLAGS AND NOT NSX_PREBUILT_ABI_FLAGS STREQUAL NSX_ABI_FLAGS)
        message(FATAL_ERROR "Prebuilt ABI mismatch. prebuilt=${NSX_PREBUILT_ABI_FLAGS}, board=${NSX_ABI_FLAGS}")
    endif()
endfunction()

function(nsx_add_segger_targets app_target)
    if(NOT TARGET ${app_target})
        message(FATAL_ERROR "nsx_add_segger_targets: target does not exist: ${app_target}")
    endif()

    if(NOT DEFINED NSX_SEGGER_DEVICE OR NOT DEFINED NSX_SEGGER_IF_SPEED OR
       NOT DEFINED NSX_SEGGER_PF_ADDR OR NOT DEFINED NSX_SEGGER_CPUFREQ OR
       NOT DEFINED NSX_SEGGER_SWOFREQ)
        message(WARNING "SEGGER configuration missing; flash/reset/view targets for ${app_target} will be stubs.")
        set(NSX_SEGGER_CONFIG_OK OFF)
    else()
        set(NSX_SEGGER_CONFIG_OK ON)
    endif()

    find_program(NSX_JLINK_EXE NAMES JLinkExe JLink JLink.exe)
    find_program(NSX_JLINK_SWO_EXE NAMES JLinkSWOViewerCL JLinkSWOViewer_CL JLinkSWOViewerCL.exe JLinkSWOViewer_CL.exe)

    if(NOT NSX_JLINK_EXE)
        message(WARNING "JLink executable not found; flash/reset targets for ${app_target} will be unavailable.")
    endif()
    if(NOT NSX_JLINK_SWO_EXE)
        message(WARNING "JLink SWO viewer not found; view target for ${app_target} will be unavailable.")
    endif()

    if(NOT DEFINED NSX_CMAKE_DIR)
        set(NSX_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}")
    endif()

    set(jlink_dir "${CMAKE_CURRENT_BINARY_DIR}/jlink/${app_target}")
    file(MAKE_DIRECTORY "${jlink_dir}")

    set(NSX_JLINK_BIN_FILE "${CMAKE_CURRENT_BINARY_DIR}/${app_target}.bin")
    if(NSX_SEGGER_CONFIG_OK)
        configure_file(
            "${NSX_CMAKE_DIR}/segger/templates/flash_cmds.jlink.in"
            "${jlink_dir}/flash_cmds.jlink"
            @ONLY
        )
        configure_file(
            "${NSX_CMAKE_DIR}/segger/templates/reset_cmds.jlink.in"
            "${jlink_dir}/reset_cmds.jlink"
            @ONLY
        )
    endif()

    if(NSX_SEGGER_CONFIG_OK AND NSX_JLINK_EXE)
        add_custom_target(${app_target}_flash
            COMMAND ${NSX_JLINK_EXE} -nogui 1 -device ${NSX_SEGGER_DEVICE} -if SWD -speed ${NSX_SEGGER_IF_SPEED} -commandfile "${jlink_dir}/flash_cmds.jlink"
            DEPENDS ${app_target}
            COMMENT "Flashing ${app_target} with SEGGER J-Link")

        add_custom_target(${app_target}_reset
            COMMAND ${NSX_JLINK_EXE} -nogui 1 -device ${NSX_SEGGER_DEVICE} -if SWD -speed ${NSX_SEGGER_IF_SPEED} -commandfile "${jlink_dir}/reset_cmds.jlink"
            COMMENT "Resetting target with SEGGER J-Link")
    else()
        add_custom_target(${app_target}_flash
            COMMAND ${CMAKE_COMMAND} -E echo "SEGGER config/JLink missing; cannot flash ${app_target}."
            COMMAND ${CMAKE_COMMAND} -E false)

        add_custom_target(${app_target}_reset
            COMMAND ${CMAKE_COMMAND} -E echo "SEGGER config/JLink missing; cannot reset ${app_target}."
            COMMAND ${CMAKE_COMMAND} -E false)
    endif()

    if(NSX_SEGGER_CONFIG_OK AND NSX_JLINK_SWO_EXE)
        add_custom_target(${app_target}_view
            COMMAND ${NSX_JLINK_SWO_EXE} -device ${NSX_SEGGER_DEVICE} -cpufreq ${NSX_SEGGER_CPUFREQ} -swofreq ${NSX_SEGGER_SWOFREQ} -itmport 0
            COMMENT "Opening SEGGER SWO viewer for ${app_target}")
    else()
        add_custom_target(${app_target}_view
            COMMAND ${CMAKE_COMMAND} -E echo "SEGGER config/SWO viewer missing; cannot view SWO for ${app_target}."
            COMMAND ${CMAKE_COMMAND} -E false)
    endif()
endfunction()
