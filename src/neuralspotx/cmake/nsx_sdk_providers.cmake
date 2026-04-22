function(_nsx_pick_first_existing out_var)
    foreach(candidate IN LISTS ARGN)
        if(EXISTS "${candidate}")
            set(${out_var} "${candidate}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${out_var} "" PARENT_SCOPE)
endfunction()

function(nsx_select_sdk_provider board_name)
    set(NSX_SDK_PROVIDER "" CACHE STRING "SDK provider module (ambiqsuite-r3|ambiqsuite-r4|ambiqsuite-r5)")
    set_property(CACHE NSX_SDK_PROVIDER PROPERTY STRINGS ambiqsuite-r3 ambiqsuite-r4 ambiqsuite-r5)

    set(NSX_AMBIQSUITE_R3_ROOT "" CACHE PATH "Path to AmbiqSuite R3 root")
    set(NSX_AMBIQSUITE_R4_ROOT "" CACHE PATH "Path to AmbiqSuite R4 root")
    set(NSX_AMBIQSUITE_R5_ROOT "" CACHE PATH "Path to AmbiqSuite R5 root")

    if(NSX_SDK_PROVIDER STREQUAL "")
        if(
            board_name STREQUAL "apollo3_evb"
            OR board_name STREQUAL "apollo3_evb_cygnus"
            OR board_name STREQUAL "apollo3p_evb"
            OR board_name STREQUAL "apollo3p_evb_cygnus"
        )
            set(NSX_SDK_PROVIDER "ambiqsuite-r3")
        elseif(
            board_name STREQUAL "apollo4b_blue_evb"
            OR board_name STREQUAL "apollo4l_evb"
            OR board_name STREQUAL "apollo4l_blue_evb"
            OR board_name STREQUAL "apollo4p_evb"
            OR board_name STREQUAL "apollo4p_blue_kbr_evb"
            OR board_name STREQUAL "apollo4p_blue_kxr_evb"
        )
            set(NSX_SDK_PROVIDER "ambiqsuite-r4")
        elseif(
            board_name STREQUAL "apollo5b_evb"
            OR board_name STREQUAL "apollo510_evb"
            OR board_name STREQUAL "apollo510b_evb"
            OR board_name STREQUAL "apollo330mP_evb"
        )
            set(NSX_SDK_PROVIDER "ambiqsuite-r5")
        else()
            message(FATAL_ERROR
                "Unable to infer SDK provider for board '${board_name}'. "
                "Set -DNSX_SDK_PROVIDER=ambiqsuite-r3|ambiqsuite-r4|ambiqsuite-r5."
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
            "Default module-local roots are used for R3/R4/R5 if vendored payload is present."
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
