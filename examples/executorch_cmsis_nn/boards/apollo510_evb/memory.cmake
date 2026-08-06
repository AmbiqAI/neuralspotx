# Role fragment: memory. Startup/system sources + linker-script selection.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo510.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510/armclang/linker_script_sbl.sct")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510/armclang/linker_script_itcm_sbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo510/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo510.c")
    set(_nsx_linker_script_default "${NSX_CORE_DIR}/src/apollo510/gcc/linker_script_sbl.ld")
    set(_nsx_linker_script_itcm "${NSX_CORE_DIR}/src/apollo510/gcc/linker_script_itcm_sbl.ld")
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
