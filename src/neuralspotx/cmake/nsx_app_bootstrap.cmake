include(CMakeParseArguments)

set(NSX_APP_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}")
get_filename_component(NSX_APP_ROOT "${NSX_APP_CMAKE_DIR}/../.." ABSOLUTE)

function(nsx_module_dir_for_name out_var module_name)
    if(module_name STREQUAL "nsx-ambiqsuite-r3")
        set(result "modules/nsx-ambiqsuite-r3")
    elseif(module_name STREQUAL "nsx-ambiqsuite-r4")
        set(result "modules/nsx-ambiqsuite-r4")
    elseif(module_name STREQUAL "nsx-ambiqsuite-r5")
        set(result "modules/nsx-ambiqsuite-r5")
    elseif(module_name STREQUAL "nsx-ambiq-hal-r3")
        set(result "modules/nsx-ambiq-hal-r3")
    elseif(module_name STREQUAL "nsx-ambiq-hal-r4")
        set(result "modules/nsx-ambiq-hal-r4")
    elseif(module_name STREQUAL "nsx-ambiq-hal-r5")
        set(result "modules/nsx-ambiq-hal-r5")
    elseif(module_name STREQUAL "nsx-ambiq-bsp-r3")
        set(result "modules/nsx-ambiq-bsp-r3")
    elseif(module_name STREQUAL "nsx-ambiq-bsp-r4")
        set(result "modules/nsx-ambiq-bsp-r4")
    elseif(module_name STREQUAL "nsx-ambiq-bsp-r5")
        set(result "modules/nsx-ambiq-bsp-r5")
    elseif(module_name STREQUAL "nsx-soc-hal")
        set(result "modules/nsx-soc-hal")
    elseif(module_name STREQUAL "nsx-cmsis-startup")
        set(result "modules/nsx-cmsis-startup")
    elseif(module_name STREQUAL "nsx-core")
        set(result "modules/nsx-core")
    elseif(module_name STREQUAL "nsx-harness")
        set(result "modules/nsx-harness")
    elseif(module_name STREQUAL "nsx-utils")
        set(result "modules/nsx-utils")
    elseif(module_name STREQUAL "nsx-peripherals")
        set(result "modules/nsx-peripherals")
    elseif(module_name STREQUAL "nsx-portable-api")
        set(result "modules/nsx-portable-api")
    else()
        set(result "")
    endif()

    set(${out_var} "${result}" PARENT_SCOPE)
endfunction()


function(nsx_add_module_subdirectory nsx_app_root module_name)
    nsx_module_dir_for_name(module_dir "${module_name}")
    if(module_dir STREQUAL "")
        return()
    endif()

    string(REPLACE "-" "_" module_build_dir "${module_name}")
    add_subdirectory(
        "${nsx_app_root}/${module_dir}"
        "${CMAKE_CURRENT_BINARY_DIR}/_nsx/${module_build_dir}"
    )
endfunction()


function(nsx_bootstrap_app)
    cmake_parse_arguments(
        NSX
        ""
        "APP_ROOT;BOARD"
        "MODULES"
        ${ARGN}
    )

    if(NSX_APP_ROOT STREQUAL "")
        message(FATAL_ERROR "nsx_bootstrap_app requires APP_ROOT")
    endif()
    if(NSX_BOARD STREQUAL "")
        message(FATAL_ERROR "nsx_bootstrap_app requires BOARD")
    endif()

    get_filename_component(NSX_ROOT "${NSX_APP_ROOT}" ABSOLUTE)
    get_filename_component(NSX_WORKSPACE_ROOT "${NSX_ROOT}/.." ABSOLUTE)
    set(NSX_CMAKE_DIR "${NSX_APP_CMAKE_DIR}")
    set(NSX_BOARD "${NSX_BOARD}")
    set(NSX_ROOT "${NSX_ROOT}" PARENT_SCOPE)
    set(NSX_CMAKE_DIR "${NSX_CMAKE_DIR}" PARENT_SCOPE)

    include("${NSX_CMAKE_DIR}/nsx_helpers.cmake")
    include("${NSX_CMAKE_DIR}/nsx_sdk_providers.cmake")

    nsx_select_sdk_provider("${NSX_BOARD}")
    include("${NSX_ROOT}/boards/${NSX_BOARD}/board.cmake")

    foreach(var
        NSX_SEGGER_DEVICE
        NSX_SEGGER_IF_SPEED
        NSX_SEGGER_PF_ADDR
        NSX_SEGGER_CPUFREQ
        NSX_SEGGER_SWOFREQ
    )
        if(DEFINED ${var})
            set(${var} "${${var}}" PARENT_SCOPE)
        endif()
    endforeach()

    foreach(module_name IN LISTS NSX_MODULES)
        nsx_add_module_subdirectory("${NSX_ROOT}" "${module_name}")
    endforeach()

    if(NOT DEFINED NSX_BOARD_TARGET)
        message(FATAL_ERROR "Board did not define NSX_BOARD_TARGET.")
    endif()
    if(NOT DEFINED NSX_SELECTED_SDK_TARGET)
        message(FATAL_ERROR "SDK provider target was not selected.")
    endif()

    target_link_libraries(${NSX_BOARD_TARGET} INTERFACE
        ${NSX_SELECTED_SDK_TARGET}
        nsx_soc_hal
        nsx_startup
    )
endfunction()


function(nsx_finalize_app app_target)
    if(NOT TARGET ${app_target})
        message(FATAL_ERROR "nsx_finalize_app target does not exist: ${app_target}")
    endif()

    target_link_options(${app_target} PRIVATE
        -Wl,-Map,$<TARGET_FILE_DIR:${app_target}>/${app_target}.map
        -Wl,--start-group
        -lm
        -lc
        -lgcc
        -lnosys
        -lstdc++
        -Wl,--end-group
    )

    if(CMAKE_OBJCOPY)
        add_custom_command(TARGET ${app_target} POST_BUILD
            COMMAND ${CMAKE_OBJCOPY} -Obinary $<TARGET_FILE:${app_target}> $<TARGET_FILE_DIR:${app_target}>/${app_target}.bin
            COMMENT "Generating ${app_target}.bin")
    endif()

    if(CMAKE_SIZE)
        add_custom_command(TARGET ${app_target} POST_BUILD
            COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${app_target}>
            COMMENT "Printing image size")
    endif()

    nsx_add_segger_targets(${app_target})
endfunction()
