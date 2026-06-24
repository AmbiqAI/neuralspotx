# Role fragment: memory. Startup/system sources + linker-script selection.
nsx_module_dir_for_name(_nsx_core_module_dir "nsx-core")
set(NSX_CORE_DIR "${NSX_ROOT}/${_nsx_core_module_dir}")

set(NSX_STARTUP_SOURCE "${NSX_CORE_DIR}/src/apollo3/gcc/startup_gcc.c")
set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_apollo3.c")
set(NSX_LINKER_SCRIPT "${NSX_CORE_DIR}/src/apollo3/gcc/linker_script.ld")
