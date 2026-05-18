function(_nsx_pick_first_existing out_var)
    foreach(candidate IN LISTS ARGN)
        if(EXISTS "${candidate}")
            set(${out_var} "${candidate}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${out_var} "" PARENT_SCOPE)
endfunction()

# Board → SDK provider mapping is generated from
# src/neuralspotx/constants.py (BOARD_SDK_PROVIDER) by
# scripts/gen_board_table.py. Keep this include relative to this file.
include("${CMAKE_CURRENT_LIST_DIR}/nsx_board_table.cmake")

function(nsx_select_sdk_provider board_name)
    set(NSX_SDK_PROVIDER "" CACHE STRING "SDK provider module (ambiqsuite-r3|ambiqsuite-r4|ambiqsuite-r5|ambiqsuite-r6)")
    set_property(CACHE NSX_SDK_PROVIDER PROPERTY STRINGS ambiqsuite-r3 ambiqsuite-r4 ambiqsuite-r5 ambiqsuite-r6)

    set(NSX_AMBIQSUITE_R3_ROOT "" CACHE PATH "Path to AmbiqSuite R3 root")
    set(NSX_AMBIQSUITE_R4_ROOT "" CACHE PATH "Path to AmbiqSuite R4 root")
    set(NSX_AMBIQSUITE_R5_ROOT "" CACHE PATH "Path to AmbiqSuite R5 root")
    set(NSX_AMBIQSUITE_R6_ROOT "" CACHE PATH "Path to AmbiqSuite R6 root")

    if(NSX_SDK_PROVIDER STREQUAL "")
        nsx_lookup_sdk_provider("${board_name}" NSX_SDK_PROVIDER)
        if(NSX_SDK_PROVIDER STREQUAL "")
            message(FATAL_ERROR
                "Unable to infer SDK provider for board '${board_name}'. "
                "Set -DNSX_SDK_PROVIDER=ambiqsuite-r3|ambiqsuite-r4|ambiqsuite-r5|ambiqsuite-r6."
            )
        endif()
    endif()

    if(NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r3")
        set(version "R3.1.1")
        set(module_default_root "${NSX_ROOT}/modules/nsx-ambiqsuite-r3/sdk")
        if(NSX_AMBIQSUITE_R3_ROOT STREQUAL "")
            _nsx_pick_first_existing(
                NSX_AMBIQSUITE_R3_ROOT_CANDIDATE
                "${module_default_root}"
            )
            if(NOT NSX_AMBIQSUITE_R3_ROOT_CANDIDATE STREQUAL "")
                set(NSX_AMBIQSUITE_R3_ROOT "${NSX_AMBIQSUITE_R3_ROOT_CANDIDATE}" CACHE PATH "Path to AmbiqSuite R3 root" FORCE)
            endif()
        endif()
        set(root "${NSX_AMBIQSUITE_R3_ROOT}")
        set(selected_target "nsx_sdk_ambiqsuite_r3")
    elseif(NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r4")
        set(version "R4.5.0")
        set(module_default_root "${NSX_ROOT}/modules/nsx-ambiqsuite-r4/sdk")
        if(NSX_AMBIQSUITE_R4_ROOT STREQUAL "")
            _nsx_pick_first_existing(
                NSX_AMBIQSUITE_R4_ROOT_CANDIDATE
                "${module_default_root}"
            )
            if(NOT NSX_AMBIQSUITE_R4_ROOT_CANDIDATE STREQUAL "")
                set(NSX_AMBIQSUITE_R4_ROOT "${NSX_AMBIQSUITE_R4_ROOT_CANDIDATE}" CACHE PATH "Path to AmbiqSuite R4 root" FORCE)
            endif()
        endif()
        set(root "${NSX_AMBIQSUITE_R4_ROOT}")
        set(selected_target "nsx_sdk_ambiqsuite_r4")
    elseif(NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r5")
        set(version "R5.3.0")
        set(module_default_root "${NSX_ROOT}/modules/nsx-ambiqsuite-r5/sdk")
        if(NSX_AMBIQSUITE_R5_ROOT STREQUAL "")
            _nsx_pick_first_existing(
                NSX_AMBIQSUITE_R5_ROOT_CANDIDATE
                "${module_default_root}"
            )
            if(NOT NSX_AMBIQSUITE_R5_ROOT_CANDIDATE STREQUAL "")
                set(NSX_AMBIQSUITE_R5_ROOT "${NSX_AMBIQSUITE_R5_ROOT_CANDIDATE}" CACHE PATH "Path to AmbiqSuite R5 root" FORCE)
            endif()
        endif()
        set(root "${NSX_AMBIQSUITE_R5_ROOT}")
        set(selected_target "nsx_sdk_ambiqsuite_r5")
    elseif(NSX_SDK_PROVIDER STREQUAL "ambiqsuite-r6")
        set(version "R6.1.0")
        set(module_default_root "${NSX_ROOT}/modules/nsx-ambiqsuite-r6/sdk")
        if(NSX_AMBIQSUITE_R6_ROOT STREQUAL "")
            _nsx_pick_first_existing(
                NSX_AMBIQSUITE_R6_ROOT_CANDIDATE
                "${module_default_root}"
            )
            if(NOT NSX_AMBIQSUITE_R6_ROOT_CANDIDATE STREQUAL "")
                set(NSX_AMBIQSUITE_R6_ROOT "${NSX_AMBIQSUITE_R6_ROOT_CANDIDATE}" CACHE PATH "Path to AmbiqSuite R6 root" FORCE)
            endif()
        endif()
        set(root "${NSX_AMBIQSUITE_R6_ROOT}")
        set(selected_target "nsx_sdk_ambiqsuite_r6")
    else()
        message(FATAL_ERROR "Unsupported NSX_SDK_PROVIDER='${NSX_SDK_PROVIDER}'")
    endif()

    if(root STREQUAL "")
        message(FATAL_ERROR
            "SDK provider '${NSX_SDK_PROVIDER}' selected for board '${board_name}', "
            "but AmbiqSuite root is not configured.\n"
            "Set one of:\n"
            "  -DNSX_AMBIQSUITE_R3_ROOT=...\n"
            "  -DNSX_AMBIQSUITE_R4_ROOT=...\n"
            "  -DNSX_AMBIQSUITE_R5_ROOT=...\n"
            "  -DNSX_AMBIQSUITE_R6_ROOT=...\n"
            "Default module-local roots are used for R3/R4/R5/R6 if vendored payload is present."
        )
    endif()

    if(NOT EXISTS "${root}")
        message(FATAL_ERROR "Configured SDK root does not exist: ${root}")
    endif()

    set(NSX_AMBIQSUITE_ROOT "${root}" PARENT_SCOPE)
    set(NSX_AMBIQSUITE_VERSION "${version}" PARENT_SCOPE)
    set(NSX_SDK_PROVIDER "${NSX_SDK_PROVIDER}" PARENT_SCOPE)
    set(NSX_SELECTED_SDK_TARGET "${selected_target}" PARENT_SCOPE)
endfunction()
