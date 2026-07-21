# Role fragment: memory. Startup/system sources + linker-script selection.
# GCC is the only declared toolchain for this board today. The armclang branch
# reuses the GCC assets so the board contract remains self-consistent until
# dedicated scatter/startup files are added.
set(_nsx_atomiq110_board_dir "${NSX_ROOT}/boards/atomiq110_fpga_turbo")

if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    set(NSX_STARTUP_SOURCE "${_nsx_atomiq110_board_dir}/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_atomiq110.c")
    set(NSX_LINKER_SCRIPT "${_nsx_atomiq110_board_dir}/gcc/linker_script.ld")
else()
    set(NSX_STARTUP_SOURCE "${_nsx_atomiq110_board_dir}/gcc/startup_gcc.c")
    set(NSX_SYSTEM_SOURCE "${NSX_AMBIQSUITE_ROOT}/CMSIS/AmbiqMicro/Source/system_atomiq110.c")
    set(NSX_LINKER_SCRIPT "${_nsx_atomiq110_board_dir}/gcc/linker_script.ld")
endif()