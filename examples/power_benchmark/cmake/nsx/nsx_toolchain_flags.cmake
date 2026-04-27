# nsx_toolchain_flags.cmake
#
# Provides nsx_apply_toolchain_flags(<flags_target>) to set compile options,
# link options, and compile definitions that differ between GCC, armclang,
# and ATfE (Arm Toolchain for Embedded / LLVM clang).
#
# Expects the following variables to be set by the including board.cmake:
#   NSX_CPU            - e.g. "cortex-m55"
#   NSX_FLOAT_ABI      - e.g. "hard"
#   NSX_FPU            - e.g. "fpv4-sp-d16" (Cortex-M4 only, optional)
#   NSX_LINKER_SCRIPT  - path to .ld (GCC/ATfE) or .sct (armclang) linker script
#
# NSX_TOOLCHAIN_FAMILY is detected from the active CMake compiler.

# --- Detect toolchain family from the compiler in use ---
if(CMAKE_C_COMPILER_ID STREQUAL "ARMClang" OR CMAKE_C_COMPILER_ID STREQUAL "ArmClang")
    set(NSX_TOOLCHAIN_FAMILY "armclang")
elseif(CMAKE_C_COMPILER_ID STREQUAL "Clang")
    # ATfE (upstream LLVM clang).  Uses lld + GCC linker scripts + newlib overlay.
    set(NSX_TOOLCHAIN_FAMILY "atfe")
elseif(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    set(NSX_TOOLCHAIN_FAMILY "gcc")
else()
    message(WARNING "Unknown C compiler '${CMAKE_C_COMPILER_ID}', assuming GCC-compatible.")
    set(NSX_TOOLCHAIN_FAMILY "gcc")
endif()


function(nsx_apply_toolchain_flags flags_target)
    # ---- Architecture flags (shared) ----
    set(_arch_flags -mthumb -mcpu=${NSX_CPU} -mfloat-abi=${NSX_FLOAT_ABI})
    if(DEFINED NSX_FPU AND NOT NSX_FPU STREQUAL "")
        list(APPEND _arch_flags -mfpu=${NSX_FPU})
    endif()

    if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
        # --------------------------------------------------------
        # Arm Compiler 6 (armclang + armlink)
        # --------------------------------------------------------
        target_compile_options(${flags_target} INTERFACE
            ${_arch_flags}
            -fshort-enums
            -ffunction-sections
            -fdata-sections
            -fno-exceptions
            -Wall
            -g
            -Ofast
            # AmbiqSuite headers use C-style string literal concatenation
            # without a space, which C++11 treats as a user-defined literal.
            $<$<COMPILE_LANGUAGE:CXX>:-Wno-reserved-user-defined-literal>
        )

        target_compile_definitions(${flags_target} INTERFACE
            NSX_TOOLCHAIN_ARMCLANG
        )

        target_link_options(${flags_target} INTERFACE
            --cpu=${NSX_CPU}
            --entry=Reset_Handler
            --remove
            "SHELL:--keep=*(RESET)"
            "SHELL:--diag_suppress 6236"
            --map
            --symbols
            --scatter=${NSX_LINKER_SCRIPT}
        )

    elseif(NSX_TOOLCHAIN_FAMILY STREQUAL "atfe")
        # --------------------------------------------------------
        # ATfE (clang + lld, newlib overlay)
        # Reuses GCC linker scripts (.ld) and GCC startup files.
        # --------------------------------------------------------
        target_compile_options(${flags_target} INTERFACE
            ${_arch_flags}
            -fshort-enums
            -ffunction-sections
            -fdata-sections
            -fomit-frame-pointer
            -fno-exceptions
            -Wall
            -g
            -O3
            -ffast-math
        )

        target_compile_definitions(${flags_target} INTERFACE
            gcc
            NSX_TOOLCHAIN_ATFE
        )

        target_link_options(${flags_target} INTERFACE
            ${_arch_flags}
            -nostartfiles
            -static
            -fno-exceptions
            -Wl,--gc-sections,--entry,Reset_Handler
            -Wl,--wrap=_write_r
            -Wl,--wrap=_close_r
            -Wl,--wrap=_lseek_r
            -Wl,--wrap=_read_r
            -Wl,--wrap=_kill_r
            -Wl,--wrap=_getpid_r
            -Wl,--wrap=_fstat_r
            -Wl,--wrap=_isatty_r
            -T${NSX_LINKER_SCRIPT}
        )

    else()
        # --------------------------------------------------------
        # GCC (arm-none-eabi-gcc + arm-none-eabi-ld)
        # --------------------------------------------------------
        target_compile_options(${flags_target} INTERFACE
            ${_arch_flags}
            -ffunction-sections
            -fdata-sections
            -fomit-frame-pointer
            -fno-exceptions
            -MMD
            -MP
            -Wall
            -g
            -O3
            -ffast-math
        )

        target_compile_definitions(${flags_target} INTERFACE
            gcc
        )

        target_link_options(${flags_target} INTERFACE
            ${_arch_flags}
            -nostartfiles
            -static
            -fno-exceptions
            -Wl,--gc-sections,--entry,Reset_Handler
            -Wl,--wrap=_write_r
            -Wl,--wrap=_close_r
            -Wl,--wrap=_lseek_r
            -Wl,--wrap=_read_r
            -Wl,--wrap=_kill_r
            -Wl,--wrap=_getpid_r
            -Wl,--wrap=_fstat_r
            -Wl,--wrap=_isatty_r
            -T${NSX_LINKER_SCRIPT}
        )
    endif()
endfunction()
