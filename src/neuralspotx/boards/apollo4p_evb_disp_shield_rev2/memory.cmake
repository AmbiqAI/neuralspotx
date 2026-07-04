# Role fragment: memory. Startup/system sources + linker-script selection.
# Same silicon/package as apollo4p_evb, so the same startup/system/linker
# sources apply.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4p/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4p/armclang/linker_script.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4p/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo4p.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4p/gcc/linker_script.ld")
endif()
