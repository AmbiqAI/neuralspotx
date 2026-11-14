# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# Initialize on include, even if this configuration registers no SEGGER targets.
# Otherwise a removed final target could retain a usable pointer and old ELF.
get_property(nsx_artifacts_initialized GLOBAL PROPERTY NSX_ARTIFACTS_INITIALIZED)
if(NOT nsx_artifacts_initialized)
    # Drop pointers to targets removed since the preceding configuration.
    file(GLOB nsx_old_artifacts "${CMAKE_BINARY_DIR}/nsx-artifacts/*.path")
    if(nsx_old_artifacts)
        file(REMOVE ${nsx_old_artifacts})
    endif()
    set_property(GLOBAL PROPERTY NSX_ARTIFACTS_INITIALIZED TRUE)
endif()

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

    # Custom boards deliberately clear inherited probe settings until verified.
    # DEFINED alone accepts empty values (including cached values).
    set(NSX_SEGGER_CONFIG_OK ON)
    foreach(setting NSX_SEGGER_DEVICE NSX_SEGGER_IF_SPEED NSX_SEGGER_PF_ADDR
                    NSX_SEGGER_CPUFREQ NSX_SEGGER_SWOFREQ)
        string(STRIP "${${setting}}" setting_value)
        if(setting_value STREQUAL "")
            message(WARNING "${setting} is missing or empty; set verified board debug settings and rerun nsx configure. flash/reset/view targets for ${app_target} will be stubs.")
            set(NSX_SEGGER_CONFIG_OK OFF)
        endif()
    endforeach()

    # Resolved board facts for app-aware reset. FORCE also clears a previous
    # board's values when the current configuration omits a setting.
    set(NSX_RESET_BOARD "${NSX_BOARD}" CACHE INTERNAL "Board owning reset settings" FORCE)
    set(NSX_RESET_DEVICE "${NSX_SEGGER_DEVICE}" CACHE INTERNAL "Resolved reset device" FORCE)
    set(NSX_RESET_SPEED_KHZ "${NSX_SEGGER_IF_SPEED}" CACHE INTERNAL "Resolved reset speed" FORCE)

    # CMake resolves the actual executable, including toolchain suffix and
    # app-specific output name/directory. Build-root location also covers
    # executable targets declared in subdirectories.
    get_target_property(nsx_target_type ${app_target} TYPE)
    if(nsx_target_type STREQUAL "EXECUTABLE")
        file(GENERATE
            OUTPUT "${CMAKE_BINARY_DIR}/nsx-artifacts/${app_target}.path"
            CONTENT "$<TARGET_FILE:${app_target}>\n")
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
    # A single failing command also works when nsx view extracts it from Ninja.
    # An echo followed by a separate false command can lose its failure status.
    file(WRITE "${jlink_dir}/unavailable.cmake"
        "message(FATAL_ERROR \"SEGGER settings or tool missing. Set verified board debug settings, install the required SEGGER tool, and rerun nsx configure.\")\n")

    set(NSX_JLINK_USB_ARGS "")
    if(DEFINED NSX_JLINK_SERIAL AND NOT NSX_JLINK_SERIAL STREQUAL "")
        set(NSX_JLINK_USB_ARGS -USB ${NSX_JLINK_SERIAL})
    endif()

    set(NSX_JLINK_BIN_FILE "${CMAKE_CURRENT_BINARY_DIR}/${app_target}.bin")
    # Do not leave scripts from a previously configured board available.
    file(REMOVE "${jlink_dir}/flash_cmds.jlink" "${jlink_dir}/reset_cmds.jlink")
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
            COMMAND ${NSX_JLINK_EXE} ${NSX_JLINK_USB_ARGS} -nogui 1 -device ${NSX_SEGGER_DEVICE} -if SWD -speed ${NSX_SEGGER_IF_SPEED} -commandfile "${jlink_dir}/flash_cmds.jlink"
            DEPENDS ${app_target}
            COMMENT "Flashing ${app_target} with SEGGER J-Link")

        add_custom_target(${app_target}_reset
            COMMAND ${NSX_JLINK_EXE} ${NSX_JLINK_USB_ARGS} -nogui 1 -device ${NSX_SEGGER_DEVICE} -if SWD -speed ${NSX_SEGGER_IF_SPEED} -commandfile "${jlink_dir}/reset_cmds.jlink"
            COMMENT "Resetting target with SEGGER J-Link")
    else()
        add_custom_target(${app_target}_flash
            COMMAND ${CMAKE_COMMAND} -P "${jlink_dir}/unavailable.cmake")

        add_custom_target(${app_target}_reset
            COMMAND ${CMAKE_COMMAND} -P "${jlink_dir}/unavailable.cmake")
    endif()

    if(NSX_SEGGER_CONFIG_OK AND NSX_JLINK_SWO_EXE)
        add_custom_target(${app_target}_view
            COMMAND ${NSX_JLINK_SWO_EXE} ${NSX_JLINK_USB_ARGS} -device ${NSX_SEGGER_DEVICE} -cpufreq ${NSX_SEGGER_CPUFREQ} -swofreq ${NSX_SEGGER_SWOFREQ} -itmport 0
            COMMENT "Opening SEGGER SWO viewer for ${app_target}")
    else()
        add_custom_target(${app_target}_view
            COMMAND ${CMAKE_COMMAND} -P "${jlink_dir}/unavailable.cmake")
    endif()
endfunction()
