include(CMakeParseArguments)

set(NSX_APP_CMAKE_DIR "${CMAKE_CURRENT_LIST_DIR}")
get_filename_component(NSX_APP_ROOT "${NSX_APP_CMAKE_DIR}/../.." ABSOLUTE)

function(nsx_module_dir_for_name out_var module_name)
    string(REPLACE "-" "_" module_var "${module_name}")
    set(module_dir_var "NSX_APP_MODULE_DIR_${module_var}")
    if(DEFINED ${module_dir_var})
        set(${out_var} "${${module_dir_var}}" PARENT_SCOPE)
        return()
    endif()
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
    # Bring each vendored project's own CMake helpers into scope. A
    # consolidated SDK bundle (e.g. nsx-ambiq-sdk) ships its assert/
    # select/toolchain helpers under <project>/cmake/*.cmake; the vendored
    # module CMakeLists call them, so they must be included before any
    # module add_subdirectory(). NSX_APP_PROJECT_DIRS is emitted by Python
    # into modules.cmake (one entry per distinct vendored project root).
    foreach(project_dir IN LISTS NSX_APP_PROJECT_DIRS)
        file(GLOB nsx_project_helpers CONFIGURE_DEPENDS "${NSX_ROOT}/${project_dir}/cmake/*.cmake")
        foreach(nsx_project_helper IN LISTS nsx_project_helpers)
            include("${nsx_project_helper}")
        endforeach()
    endforeach()
    include("${NSX_CMAKE_DIR}/nsx_sdk_providers.cmake")

    nsx_select_sdk_provider("${NSX_BOARD}")
    include("${NSX_ROOT}/boards/${NSX_BOARD}/board.cmake")

    foreach(var
        NSX_TOOLCHAIN_FAMILY
        NSX_CPU
        NSX_SOC_FAMILY
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

    # --- nsx::bsp role contract handshake (issue #154a.2) ------------------
    # The BSP producer (an SDK provider module such as nsx-ambiq-bsp) publishes
    # the provider-neutral nsx::bsp role and a contract version into the cache
    # during its add_subdirectory() above. When that seam is present we verify
    # it is compatible and wire the board target to it explicitly. Older SDK
    # snapshots predate the seam; there the board still gets BSP support
    # transitively through nsx_soc_hal, so we degrade gracefully rather than
    # forcing every pinned example to re-lock in lock step.
    set(NSX_BSP_CONTRACT_VERSION_REQUIRED 1)
    set(_nsx_bsp_link "")
    if(TARGET nsx::bsp)
        if(NOT DEFINED NSX_BSP_CONTRACT_VERSION)
            message(FATAL_ERROR
                "nsx::bsp exists but NSX_BSP_CONTRACT_VERSION was not published.")
        endif()
        if(NOT NSX_BSP_CONTRACT_VERSION EQUAL NSX_BSP_CONTRACT_VERSION_REQUIRED)
            message(FATAL_ERROR
                "nsx::bsp contract version mismatch: board requires "
                "${NSX_BSP_CONTRACT_VERSION_REQUIRED}, provider supplies "
                "${NSX_BSP_CONTRACT_VERSION}.")
        endif()
        set(_nsx_bsp_link nsx::bsp)
    endif()

    target_link_libraries(${NSX_BOARD_TARGET} INTERFACE
        ${NSX_SELECTED_SDK_TARGET}
        nsx_soc_hal
        nsx_startup
        ${_nsx_bsp_link}
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


# ---------------------------------------------------------------------------
# Per-target source overlays
# ---------------------------------------------------------------------------
# Multi-target apps keep shared sources under src/ and place the small amount
# of SoC-family-specific code under src/<soc_family>/ (e.g. src/apollo5/,
# src/apollo330/). This helper compiles only the overlay matching the active
# board's NSX_SOC_FAMILY into <app_target>, so application source stays free of
# #ifdef soup. It is a no-op when the app ships no overlay directory for the
# active family. Call after nsx_bootstrap_app() (which publishes
# NSX_SOC_FAMILY) and after add_executable().
function(nsx_target_soc_overlay app_target)
    if(NOT TARGET ${app_target})
        message(FATAL_ERROR "nsx_target_soc_overlay: target does not exist: ${app_target}")
    endif()
    if(NOT DEFINED NSX_SOC_FAMILY OR NSX_SOC_FAMILY STREQUAL "")
        return()
    endif()
    set(_overlay_dir "${NSX_ROOT}/src/${NSX_SOC_FAMILY}")
    if(NOT IS_DIRECTORY "${_overlay_dir}")
        return()
    endif()
    file(GLOB _overlay_sources CONFIGURE_DEPENDS
        "${_overlay_dir}/*.c"
        "${_overlay_dir}/*.cc"
        "${_overlay_dir}/*.cpp"
        "${_overlay_dir}/*.S"
    )
    if(_overlay_sources)
        target_sources(${app_target} PRIVATE ${_overlay_sources})
        target_include_directories(${app_target} PRIVATE "${_overlay_dir}")
        message(STATUS "nsx: ${app_target} += SoC overlay src/${NSX_SOC_FAMILY}")
    endif()
endfunction()


# ---------------------------------------------------------------------------
# Per-target linker-script overlay
# ---------------------------------------------------------------------------
# Swap the board's default ``-T`` linker script for an app-provided one on the
# active board's flags target. Encapsulates the GCC/ATfE "filter the board
# flags target's -T and append ours" pattern so apps don't hand-roll it (the
# board flags target appends after the app's own options, so the override must
# live on that interface target). armclang scatter overlays are not yet
# supported: the helper warns and keeps the board default.
function(nsx_target_linker_overlay app_target script_path)
    if(NOT TARGET ${app_target})
        message(FATAL_ERROR "nsx_target_linker_overlay: target does not exist: ${app_target}")
    endif()
    if(NOT EXISTS "${script_path}")
        message(FATAL_ERROR "nsx_target_linker_overlay: linker script not found: ${script_path}")
    endif()
    if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
        message(STATUS
            "nsx: armclang scatter overlay not supported; "
            "keeping board default linker script for ${app_target}")
        return()
    endif()
    set(_flags_target "nsx_board_${NSX_BOARD}_flags")
    if(NOT TARGET ${_flags_target})
        message(FATAL_ERROR
            "nsx_target_linker_overlay: board flags target missing: ${_flags_target}")
    endif()
    get_target_property(_link_opts ${_flags_target} INTERFACE_LINK_OPTIONS)
    if(NOT _link_opts)
        set(_link_opts "")
    endif()
    list(FILTER _link_opts EXCLUDE REGEX "^-T")
    list(APPEND _link_opts "-T${script_path}")
    set_property(TARGET ${_flags_target} PROPERTY INTERFACE_LINK_OPTIONS ${_link_opts})
    message(STATUS "nsx: ${app_target} linker overlay -> ${script_path}")
endfunction()
