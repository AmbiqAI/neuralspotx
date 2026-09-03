# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
# Role fragment: memory. Startup/system sources + linker-script selection.
# The FPGA turbo board loads directly via J-Link with no secure bootloader,
# so the default profile is the "nbl" (no-bootloader) script set shipped by
# nsx-core; the "sbl" variants are reserved for future silicon.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/atomiq110/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_atomiq110.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/atomiq110/armclang/linker_script_nbl.sct")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/atomiq110/armclang/linker_script_itcm_nbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/atomiq110/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_atomiq110.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/atomiq110/gcc/linker_script_nbl.ld")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/atomiq110/gcc/linker_script_itcm_nbl.ld")
endif()

if(NOT DEFINED NSX_LINKER_SCRIPT)
    if(COMMAND nsx_select_linker_script)
        nsx_select_linker_script(
            DEFAULT "${_nsx_linker_script_default}"
            ITCM "${_nsx_linker_script_itcm}"
        )
    else()
        # SDK predates named linker profiles — fall back to the default script.
        set(NSX_LINKER_SCRIPT "${_nsx_linker_script_default}")
    endif()
endif()
