function(_nsx_pick_first_existing out_var)
    foreach(candidate IN LISTS ARGN)
        if(EXISTS "${candidate}")
            set(${out_var} "${candidate}" PARENT_SCOPE)
            return()
        endif()
    endforeach()
    set(${out_var} "" PARENT_SCOPE)
endfunction()

# Resolve a module's vendored dir (relative to NSX_ROOT). The app bootstrap
# defines ``nsx_module_dir_for_name`` (which reads the generated
# ``NSX_APP_MODULE_DIR_<id>`` overlay so a consolidated SDK bundle nests
# modules under its project dir). When this file is included in isolation
# (e.g. provider unit tests), fall back to the flat ``modules/<name>`` layout.
function(_nsx_module_relpath_or_default out_var module_name)
    if(COMMAND nsx_module_dir_for_name)
        nsx_module_dir_for_name(_rel "${module_name}")
        set(${out_var} "${_rel}" PARENT_SCOPE)
    else()
        set(${out_var} "modules/${module_name}" PARENT_SCOPE)
    endif()
endfunction()

# Board → SDK provider mapping is generated from
# src/neuralspotx/constants.py (BOARD_SDK_PROVIDER) by
# scripts/gen_board_table.py. Keep this include relative to this file.
include("${CMAKE_CURRENT_LIST_DIR}/nsx_board_table.cmake")

# Resolve a board name to one the generated provider table recognises.
#
# Custom boards created by `nsx board create` are not in the generated
# table; they ship a thin `boards/<name>/board.cmake` that sets
# `NSX_PARENT_BOARD "<evb>"` and delegates to the parent EVB. SDK-provider
# selection runs before any board.cmake is included, so for an unknown
# board we walk the parent link until we reach a board the table knows,
# letting the inherited EVB's provider apply automatically. Requires
# `NSX_ROOT` to be set by the caller (the bootstrap does this).
function(_nsx_resolve_provider_board board_name out_var)
    set(_current "${board_name}")
    # Bounded walk guards against cycles and runaway inheritance chains.
    foreach(_depth RANGE 0 8)
        nsx_lookup_sdk_provider("${_current}" _provider)
        if(NOT _provider STREQUAL "")
            set(${out_var} "${_current}" PARENT_SCOPE)
            return()
        endif()
        set(_board_cmake "${NSX_ROOT}/boards/${_current}/board.cmake")
        if(NOT EXISTS "${_board_cmake}")
            break()
        endif()
        file(READ "${_board_cmake}" _board_text)
        string(REGEX MATCH "NSX_PARENT_BOARD[ \t]+\"([^\"]+)\"" _ "${_board_text}")
        set(_parent "${CMAKE_MATCH_1}")
        if(_parent STREQUAL "" OR _parent STREQUAL "${_current}")
            break()
        endif()
        set(_current "${_parent}")
    endforeach()
    # No resolution: hand back the original name so the caller's lookup
    # fails with a clear, board-specific error message.
    set(${out_var} "${board_name}" PARENT_SCOPE)
endfunction()

function(nsx_select_sdk_provider board_name)
    set(NSX_SDK_PROVIDER "" CACHE STRING "SDK provider module (ambiqsuite)")
    set_property(CACHE NSX_SDK_PROVIDER PROPERTY STRINGS ambiqsuite)

    # Single unified AmbiqSuite root. The legacy per-train override
    # NSX_AMBIQSUITE_R*_ROOT vars are gone; use NSX_AMBIQSUITE_ROOT_OVERRIDE
    # to point at an out-of-tree SDK payload.
    set(NSX_AMBIQSUITE_ROOT_OVERRIDE "" CACHE PATH "Path to an out-of-tree AmbiqSuite root")

    if(NSX_SDK_PROVIDER STREQUAL "")
        # Follow the parent link for custom boards before giving up.
        _nsx_resolve_provider_board("${board_name}" _provider_board)
        nsx_lookup_sdk_provider("${_provider_board}" NSX_SDK_PROVIDER)
        if(NSX_SDK_PROVIDER STREQUAL "")
            message(FATAL_ERROR
                "Unable to infer SDK provider for board '${board_name}'. "
                "Set -DNSX_SDK_PROVIDER=ambiqsuite."
            )
        endif()
    endif()

    if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite")
        message(FATAL_ERROR "Unsupported NSX_SDK_PROVIDER='${NSX_SDK_PROVIDER}' (expected 'ambiqsuite').")
    endif()

    set(version "stable")
    _nsx_module_relpath_or_default(_ambiqsuite_module_dir "nsx-ambiqsuite")
    set(module_default_root "${NSX_ROOT}/${_ambiqsuite_module_dir}/sdk")
    if(NOT NSX_AMBIQSUITE_ROOT_OVERRIDE STREQUAL "")
        set(root "${NSX_AMBIQSUITE_ROOT_OVERRIDE}")
    else()
        _nsx_pick_first_existing(
            root
            "${module_default_root}"
            "${NSX_ROOT}/modules/nsx-ambiqsuite/sdk"
        )
    endif()
    set(selected_target "nsx_sdk_ambiqsuite")

    if(root STREQUAL "")
        message(FATAL_ERROR
            "SDK provider 'ambiqsuite' selected for board '${board_name}', "
            "but the AmbiqSuite root could not be located.\n"
            "Set -DNSX_AMBIQSUITE_ROOT_OVERRIDE=... or vendor the nsx-ambiqsuite "
            "module so its sdk/ payload is present."
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
