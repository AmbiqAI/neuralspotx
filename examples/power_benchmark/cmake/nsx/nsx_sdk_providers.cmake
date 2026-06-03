# SDK provider selection — a dumb consumer of facts resolved by Python.
#
# Python (neuralspotx.project_config) resolves every SDK-provider fact and
# emits them into the generated cmake/nsx/nsx_build_facts.cmake, included by
# nsx_app_bootstrap.cmake before nsx_select_sdk_provider() runs:
#
#   * NSX_BOARD_SDK_PROVIDER_<board_ident>      board id    -> provider id
#   * NSX_SDK_PROVIDER_VERSION_<provider_ident> provider id -> sdk release
#
# Module directories come from the generated modules.cmake
# (NSX_MODULE_DIR_<module_ident>). This file therefore parses no YAML and
# guesses no paths — it only derives per-tier identifier strings and reads the
# facts above.

# Derive the provider module root ("<module>/sdk") from the module dir variable
# emitted by modules.cmake. No filesystem path guessing.
function(_nsx_sdk_module_root out_var module_name)
    string(MAKE_C_IDENTIFIER "${module_name}" module_ident)
    set(module_dir_var "NSX_MODULE_DIR_${module_ident}")
    if(DEFINED ${module_dir_var})
        set(${out_var} "${NSX_ROOT}/${${module_dir_var}}/sdk" PARENT_SCOPE)
    else()
        set(${out_var} "" PARENT_SCOPE)
    endif()
endfunction()

# Single source of truth for the AmbiqSuite SDK provider tiers nsx knows how to
# bootstrap. To support a new release, add its provider id (ambiqsuite-r<N>)
# here — every per-tier identifier (module name, root cache variable, CMake
# target) is derived from the id, and the human-readable SDK release string is
# resolved by Python into nsx_build_facts.cmake. Nothing else in this file is
# release-specific.
set(NSX_SUPPORTED_SDK_PROVIDERS
    ambiqsuite-r3
    ambiqsuite-r4
    ambiqsuite-r5
    ambiqsuite-r6
)

# Derive the per-tier identifiers for an ``ambiqsuite-r<N>`` provider id.
function(_nsx_provider_identifiers provider out_module out_root_var out_target)
    if(NOT provider MATCHES "^ambiqsuite-r[0-9]+$")
        message(FATAL_ERROR
            "Unsupported SDK provider id '${provider}'. "
            "Expected one of: ${NSX_SUPPORTED_SDK_PROVIDERS}."
        )
    endif()
    set(${out_module} "nsx-${provider}" PARENT_SCOPE)
    string(REGEX REPLACE "^ambiqsuite-" "" tier "${provider}")
    string(TOUPPER "${tier}" tier_upper)
    set(${out_root_var} "NSX_AMBIQSUITE_${tier_upper}_ROOT" PARENT_SCOPE)
    string(REPLACE "-" "_" target_suffix "${provider}")
    set(${out_target} "nsx_sdk_${target_suffix}" PARENT_SCOPE)
endfunction()

# Board → SDK provider id is resolved by Python into the generated build facts
# (NSX_BOARD_SDK_PROVIDER_<board_ident>). nsx no longer scrapes the board
# manifest at configure time.
function(nsx_lookup_sdk_provider board_name out_var)
    string(MAKE_C_IDENTIFIER "${board_name}" board_ident)
    set(fact_var "NSX_BOARD_SDK_PROVIDER_${board_ident}")
    if(DEFINED ${fact_var})
        set(${out_var} "${${fact_var}}" PARENT_SCOPE)
    else()
        set(${out_var} "" PARENT_SCOPE)
    endif()
endfunction()

function(nsx_select_sdk_provider board_name)
    set(NSX_SDK_PROVIDER "" CACHE STRING "SDK provider module (${NSX_SUPPORTED_SDK_PROVIDERS})")
    set_property(CACHE NSX_SDK_PROVIDER PROPERTY STRINGS ${NSX_SUPPORTED_SDK_PROVIDERS})

    # Declare the per-tier root override cache variables up front.
    foreach(provider IN LISTS NSX_SUPPORTED_SDK_PROVIDERS)
        _nsx_provider_identifiers("${provider}" _unused_module tier_root_var _unused_target)
        set("${tier_root_var}" "" CACHE PATH "Path to AmbiqSuite ${provider} root")
    endforeach()

    if(NSX_SDK_PROVIDER STREQUAL "")
        nsx_lookup_sdk_provider("${board_name}" NSX_SDK_PROVIDER)
        if(NSX_SDK_PROVIDER STREQUAL "")
            message(FATAL_ERROR
                "Unable to infer SDK provider for board '${board_name}'. "
                "Regenerate build glue with `nsx sync`, or set "
                "-DNSX_SDK_PROVIDER to one of: ${NSX_SUPPORTED_SDK_PROVIDERS}."
            )
        endif()
    endif()

    list(FIND NSX_SUPPORTED_SDK_PROVIDERS "${NSX_SDK_PROVIDER}" provider_index)
    if(provider_index EQUAL -1)
        message(FATAL_ERROR
            "Unsupported NSX_SDK_PROVIDER='${NSX_SDK_PROVIDER}'. "
            "Supported providers: ${NSX_SUPPORTED_SDK_PROVIDERS}."
        )
    endif()

    _nsx_provider_identifiers("${NSX_SDK_PROVIDER}" provider_module root_var selected_target)

    # An explicit -D<root_var>=... wins; otherwise derive the root from the
    # vendored provider module so the path comes from the resolved module dir,
    # not a hardcoded guess.
    set(root "${${root_var}}")
    if(root STREQUAL "")
        _nsx_sdk_module_root(module_default_root "${provider_module}")
        if(NOT module_default_root STREQUAL "" AND EXISTS "${module_default_root}")
            set("${root_var}" "${module_default_root}" CACHE PATH "Path to AmbiqSuite ${NSX_SDK_PROVIDER} root" FORCE)
            set(root "${module_default_root}")
        endif()
    endif()

    if(root STREQUAL "")
        message(FATAL_ERROR
            "SDK provider '${NSX_SDK_PROVIDER}' selected for board '${board_name}', "
            "but AmbiqSuite root is not configured.\n"
            "Set -D${root_var}=...\n"
            "Or ensure modules.cmake defines NSX_MODULE_DIR for the provider module '${provider_module}'."
        )
    endif()

    if(NOT EXISTS "${root}")
        message(FATAL_ERROR "Configured SDK root does not exist: ${root}")
    endif()

    # SDK release string is resolved by Python into the generated build facts
    # (NSX_SDK_PROVIDER_VERSION_<provider_ident>). nsx no longer scrapes the
    # provider module manifest at configure time.
    string(MAKE_C_IDENTIFIER "${NSX_SDK_PROVIDER}" provider_ident)
    set(version_var "NSX_SDK_PROVIDER_VERSION_${provider_ident}")
    if(DEFINED ${version_var})
        set(version "${${version_var}}")
    else()
        set(version "")
    endif()

    set(NSX_AMBIQSUITE_ROOT "${root}" PARENT_SCOPE)
    set(NSX_AMBIQSUITE_VERSION "${version}" PARENT_SCOPE)
    set(NSX_SDK_PROVIDER "${NSX_SDK_PROVIDER}" PARENT_SCOPE)
    set(NSX_SELECTED_SDK_TARGET "${selected_target}" PARENT_SCOPE)
endfunction()
