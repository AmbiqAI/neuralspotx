# Role fragment: memory. Startup/system sources + linker-script selection.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4l/armclang/startup_keil6.s")
    set(NSX_SYSTEM_SOURCE "")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4l/armclang/linker_script.sct")
else()
    set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo4l/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "")
    set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo4l/gcc/linker_script.ld")
endif()
