# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# Called only by authored templates/examples whose baseline graph was audited.
# Keep an automatically chosen default distinct from an author's explicit opt-in.
set(_nsx_debug_default OFF)
if(NSX_BOARD STREQUAL "apollo510_evb" AND CMAKE_C_COMPILER_ID STREQUAL "GNU"
   AND CMAKE_SYSTEM_PROCESSOR STREQUAL "arm"
   AND CMAKE_VERSION VERSION_GREATER_EQUAL 3.31 AND CMAKE_GENERATOR STREQUAL "Ninja")
    set(_nsx_debug_default ON)
endif()

if(NOT DEFINED NSX_DEBUG_CONTEXT)
    set(_NSX_TEMPLATE_DEBUG_MANAGED ON CACHE INTERNAL "Template owns debug default" FORCE)
elseif(_NSX_TEMPLATE_DEBUG_MANAGED)
    # A changed preference or explicit input declaration transfers ownership
    # to the author. An unchanged automatic choice follows board/toolchain changes.
    if(NSX_DEBUG_CONTEXT)
        set(_nsx_debug_current ON)
    else()
        set(_nsx_debug_current OFF)
    endif()
    if(NOT _nsx_debug_current STREQUAL _NSX_TEMPLATE_DEBUG_LAST
       OR DEFINED NSX_DEBUG_INPUT_CONTRACT)
        set(_NSX_TEMPLATE_DEBUG_MANAGED OFF CACHE INTERNAL "Template owns debug default" FORCE)
    endif()
endif()

if(_NSX_TEMPLATE_DEBUG_MANAGED)
    set(NSX_DEBUG_CONTEXT ${_nsx_debug_default} CACHE BOOL "Prepare configured debug handoff" FORCE)
    set(_NSX_TEMPLATE_DEBUG_LAST ${_nsx_debug_default} CACHE INTERNAL "Last template debug default" FORCE)
endif()
if(_nsx_debug_default)
    # Customization carries the author obligation to register external reads.
    set(NSX_DEBUG_INPUT_CONTRACT 1)
endif()
