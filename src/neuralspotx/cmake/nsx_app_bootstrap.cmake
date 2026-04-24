include(CMakeParseArguments)

set(NSX_APP_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}")
get_filename_component(NSX_APP_ROOT "${NSX_APP_CMAKE_DIR}/../.." ABSOLUTE)

function(nsx_module_dir_for_name out_var module_name)
    set(${out_var} "modules/${module_name}" PARENT_SCOPE)
endfunction()


function(nsx_add_module_subdirectory nsx_app_root module_name)
    nsx_module_dir_for_name(module_dir "${module_name}")

    if(NOT EXISTS "${nsx_app_root}/${module_dir}")
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
    set(NSX_CMAKE_DIR "${NSX_APP_CMAKE_DIR}")
    set(NSX_BOARD "${NSX_BOARD}")
    set(NSX_ROOT "${NSX_ROOT}" PARENT_SCOPE)
    set(NSX_CMAKE_DIR "${NSX_CMAKE_DIR}" PARENT_SCOPE)

    include("${NSX_CMAKE_DIR}/nsx_helpers.cmake")
    include("${NSX_CMAKE_DIR}/nsx_sdk_providers.cmake")

    nsx_select_sdk_provider("${NSX_BOARD}")
    include("${NSX_ROOT}/boards/${NSX_BOARD}/board.cmake")

    foreach(var
        NSX_TOOLCHAIN_FAMILY
        NSX_STARTUP_SOURCE
        NSX_SYSTEM_SOURCE
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

    # armlink does not pull objects from STATIC archives when the only
    # reference is a scatter-file section selector (e.g. RESET).  Add the
    # startup sources directly to the executable so their objects appear on
    # the armlink command line.
    if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
        if(DEFINED NSX_STARTUP_SOURCE)
            target_sources(${app_target} PRIVATE ${NSX_STARTUP_SOURCE})
        endif()
        if(DEFINED NSX_SYSTEM_SOURCE AND NOT NSX_SYSTEM_SOURCE STREQUAL "")
            target_sources(${app_target} PRIVATE ${NSX_SYSTEM_SOURCE})
        endif()
    endif()

    # Ensure system libraries (-lm, -lc, etc.) appear AFTER all project
    # archives in the link command.  Pre-built static libraries such as
    # libam_hal.a contain object files that were not compiled with
    # -ffunction-sections, so the linker may pull in sections that
    # reference math symbols like fmodf.  Placing -lm before the
    # archives causes the reference to go unresolved.
    #
    # CMAKE_C_STANDARD_LIBRARIES is appended at the very end of the
    # linker invocation, after all target_link_libraries contributions.
    # armclang bundles its own runtime — no explicit stdlib linking needed.
    # ATfE uses newlib overlay via --config=newlib.cfg and compiler-rt
    # instead of libgcc, but still needs -lm -lc -lnosys.
    if(NSX_TOOLCHAIN_FAMILY STREQUAL "gcc")
        set(CMAKE_C_STANDARD_LIBRARIES
            "-Wl,--start-group -lm -lc -lgcc -lnosys -lstdc++ -Wl,--end-group"
            PARENT_SCOPE
        )
    elseif(NSX_TOOLCHAIN_FAMILY STREQUAL "atfe")
        set(CMAKE_C_STANDARD_LIBRARIES
            "-Wl,--start-group -lm -lc -lnosys -Wl,--end-group"
            PARENT_SCOPE
        )
    endif()

    if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
        # armclang: use fromelf to generate .bin and print size
        find_program(NSX_FROMELF fromelf)
        if(NSX_FROMELF)
            add_custom_command(TARGET ${app_target} POST_BUILD
                COMMAND ${NSX_FROMELF} --bin --output $<TARGET_FILE_DIR:${app_target}>/${app_target}.bin $<TARGET_FILE:${app_target}>
                COMMENT "Generating ${app_target}.bin (fromelf)")
            add_custom_command(TARGET ${app_target} POST_BUILD
                COMMAND ${NSX_FROMELF} --text -z $<TARGET_FILE:${app_target}>
                COMMENT "Printing image size (fromelf)")
        endif()
    else()
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
    endif()

    # Map file — armclang generates it via --map in link flags;
    # GCC and ATfE need an explicit -Wl,-Map option.
    if(NSX_TOOLCHAIN_FAMILY STREQUAL "gcc" OR NSX_TOOLCHAIN_FAMILY STREQUAL "atfe")
        target_link_options(${app_target} PRIVATE
            -Wl,-Map,$<TARGET_FILE_DIR:${app_target}>/${app_target}.map
        )
    endif()

    nsx_add_segger_targets(${app_target})
endfunction()
