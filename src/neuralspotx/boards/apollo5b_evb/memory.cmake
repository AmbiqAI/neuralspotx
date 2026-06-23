# Role fragment: memory. Startup/system sources + linker-script selection.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo5b/armclang/startup_keil6.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/apollo5b/system_apollo5b.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo5b/armclang/linker_script_sbl.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo5b/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/src/apollo5b/system_apollo5b.c")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo5b/gcc/linker_script_sbl.ld")
endif()
